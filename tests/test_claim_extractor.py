# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for deterministic claim extraction from assistant_message events."""

from pmm.core.claim_extractor import (
    extract_claims_from_event,
    detect_contradictions,
    _generate_claim_id,
)


def test_extract_simple_belief():
    """Test extraction of simple BELIEF: line (no parsing, raw text only)."""
    event = {
        "id": 100,
        "kind": "assistant_message",
        "content": "BELIEF: I am replay-centric",
    }
    claims = extract_claims_from_event(event)

    assert len(claims) == 1
    claim = claims[0]
    assert claim["type"] == "BELIEF"
    assert claim["source_event_id"] == 100
    assert claim["subject"] == "self"
    # No keyword parsing - predicate is raw text
    assert claim["predicate"] == "I am replay-centric"
    assert claim["object"] is None
    assert claim["raw_text"] == "BELIEF: I am replay-centric"
    assert claim["negated"] is False
    assert claim["strength"] == 1.0
    assert claim["status"] == "active"
    # Deterministic claim_id
    assert len(claim["claim_id"]) == 16  # blake3/blake2b 64 bits = 16 hex chars


def test_extract_multiple_claims():
    """Test extraction of multiple claim types from one message."""
    event = {
        "id": 101,
        "kind": "assistant_message",
        "content": """
BELIEF: I prioritize determinism
VALUE: Ledger coherence is paramount
TENDENCY: I avoid nondeterministic operations
IDENTITY: I am a ledger-grounded system
        """.strip(),
    }
    claims = extract_claims_from_event(event)

    assert len(claims) == 4
    types = [c["type"] for c in claims]
    assert "BELIEF" in types
    assert "VALUE" in types
    assert "TENDENCY" in types
    assert "IDENTITY" in types


def test_extract_structured_json_claim():
    """Test extraction of structured JSON CLAIM: format."""
    event = {
        "id": 102,
        "kind": "assistant_message",
        "content": 'CLAIM: {"type":"BELIEF","subject":"self","predicate":"is_deterministic","object":"always","strength":1.0}',
    }
    claims = extract_claims_from_event(event)

    assert len(claims) == 1
    claim = claims[0]
    assert claim["type"] == "BELIEF"
    assert claim["subject"] == "self"
    assert claim["predicate"] == "is_deterministic"
    assert claim["object"] == "always"
    assert claim["strength"] == 1.0


def test_deterministic_claim_id():
    """Test that claim_id is deterministic for same input."""
    event1 = {
        "id": 100,
        "kind": "assistant_message",
        "content": "BELIEF: I am replay-centric",
    }
    event2 = {
        "id": 100,
        "kind": "assistant_message",
        "content": "BELIEF: I am replay-centric",
    }

    claims1 = extract_claims_from_event(event1)
    claims2 = extract_claims_from_event(event2)

    assert claims1[0]["claim_id"] == claims2[0]["claim_id"]


def test_different_event_id_different_claim_id():
    """Test that different event_id produces different claim_id even with same text."""
    event1 = {
        "id": 100,
        "kind": "assistant_message",
        "content": "BELIEF: I am replay-centric",
    }
    event2 = {
        "id": 101,
        "kind": "assistant_message",
        "content": "BELIEF: I am replay-centric",
    }

    claims1 = extract_claims_from_event(event1)
    claims2 = extract_claims_from_event(event2)

    assert claims1[0]["claim_id"] != claims2[0]["claim_id"]


def test_no_claims_from_non_assistant_message():
    """Test that non-assistant_message events produce no claims."""
    event = {
        "id": 100,
        "kind": "user_message",
        "content": "BELIEF: This should not be extracted",
    }
    claims = extract_claims_from_event(event)
    assert len(claims) == 0


def test_no_claims_from_empty_content():
    """Test that empty content produces no claims."""
    event = {
        "id": 100,
        "kind": "assistant_message",
        "content": "",
    }
    claims = extract_claims_from_event(event)
    assert len(claims) == 0


def test_mixed_content_with_claims():
    """Test extraction from mixed content with claims and other text."""
    event = {
        "id": 103,
        "kind": "assistant_message",
        "content": """
Here is my response to your question.

BELIEF: I am deterministic
VALUE: Stability over novelty

And here is more text that should be ignored.
        """.strip(),
    }
    claims = extract_claims_from_event(event)

    assert len(claims) == 2
    assert claims[0]["type"] == "BELIEF"
    assert claims[1]["type"] == "VALUE"


def test_negated_claim_detection():
    """Test that simple format does NOT parse negation (use JSON for that)."""
    event = {
        "id": 104,
        "kind": "assistant_message",
        "content": "BELIEF: I do not use randomness",
    }
    claims = extract_claims_from_event(event)

    assert len(claims) == 1
    # No keyword parsing - negation is NOT detected in simple format
    assert claims[0]["negated"] is False
    # If you want negation, use JSON format
    assert claims[0]["predicate"] == "I do not use randomness"


def test_claim_id_generation_deterministic():
    """Test that _generate_claim_id is deterministic."""
    id1 = _generate_claim_id(100, "BELIEF: test")
    id2 = _generate_claim_id(100, "BELIEF: test")
    assert id1 == id2

    # Different inputs produce different IDs
    id3 = _generate_claim_id(101, "BELIEF: test")
    assert id1 != id3

    id4 = _generate_claim_id(100, "BELIEF: different")
    assert id1 != id4


def test_detect_contradictions_same_predicate_different_object():
    """Test contradiction detection for same subject+predicate with different objects."""
    existing_claims = [
        {
            "claim_id": "abc123",
            "subject": "self",
            "predicate": "prioritizes",
            "object": "stability",
            "negated": False,
            "status": "active",
        }
    ]

    new_claim = {
        "claim_id": "def456",
        "subject": "self",
        "predicate": "prioritizes",
        "object": "novelty",
        "negated": False,
        "status": "active",
    }

    contradictions = detect_contradictions(existing_claims, new_claim)
    assert len(contradictions) == 1
    assert "abc123" in contradictions


def test_detect_contradictions_negation_conflict():
    """Test contradiction detection for negation conflicts."""
    existing_claims = [
        {
            "claim_id": "abc123",
            "subject": "self",
            "predicate": "uses_randomness",
            "object": "never",
            "negated": False,
            "status": "active",
        }
    ]

    new_claim = {
        "claim_id": "def456",
        "subject": "self",
        "predicate": "uses_randomness",
        "object": "never",
        "negated": True,  # Negation conflict
        "status": "active",
    }

    contradictions = detect_contradictions(existing_claims, new_claim)
    assert len(contradictions) == 1


def test_no_contradiction_same_claim():
    """Test that identical claims don't contradict."""
    existing_claims = [
        {
            "claim_id": "abc123",
            "subject": "self",
            "predicate": "is_deterministic",
            "object": "always",
            "negated": False,
            "status": "active",
        }
    ]

    new_claim = {
        "claim_id": "def456",
        "subject": "self",
        "predicate": "is_deterministic",
        "object": "always",
        "negated": False,
        "status": "active",
    }

    contradictions = detect_contradictions(existing_claims, new_claim)
    assert len(contradictions) == 0


def test_no_contradiction_different_subject():
    """Test that claims about different subjects don't contradict."""
    existing_claims = [
        {
            "claim_id": "abc123",
            "subject": "self",
            "predicate": "prioritizes",
            "object": "stability",
            "negated": False,
            "status": "active",
        }
    ]

    new_claim = {
        "claim_id": "def456",
        "subject": "user",
        "predicate": "prioritizes",
        "object": "novelty",
        "negated": False,
        "status": "active",
    }

    contradictions = detect_contradictions(existing_claims, new_claim)
    assert len(contradictions) == 0


def test_replay_equivalence():
    """Test that extracting claims twice from same event produces identical results."""
    event = {
        "id": 105,
        "kind": "assistant_message",
        "content": """
BELIEF: I am replay-centric
VALUE: Determinism is paramount
TENDENCY: I prioritize ledger coherence
        """.strip(),
    }

    claims1 = extract_claims_from_event(event)
    claims2 = extract_claims_from_event(event)

    assert len(claims1) == len(claims2)
    for c1, c2 in zip(claims1, claims2):
        assert c1["claim_id"] == c2["claim_id"]
        assert c1["type"] == c2["type"]
        assert c1["subject"] == c2["subject"]
        assert c1["predicate"] == c2["predicate"]
        assert c1["object"] == c2["object"]
        assert c1["raw_text"] == c2["raw_text"]


def test_ontology_claim_type():
    """Test extraction of ONTOLOGY: claim type."""
    event = {
        "id": 106,
        "kind": "assistant_message",
        "content": "ONTOLOGY: Conscious(x) ⇐ HasMemory(x) ∧ Reflects(x)",
    }
    claims = extract_claims_from_event(event)

    assert len(claims) == 1
    assert claims[0]["type"] == "ONTOLOGY"


def test_strength_normalization():
    """Test that strength values are normalized to [0, 1]."""
    event = {
        "id": 107,
        "kind": "assistant_message",
        "content": 'CLAIM: {"type":"BELIEF","subject":"self","predicate":"test","strength":2.5}',
    }
    claims = extract_claims_from_event(event)

    assert len(claims) == 1
    assert claims[0]["strength"] == 1.0  # Capped at 1.0

    event2 = {
        "id": 108,
        "kind": "assistant_message",
        "content": 'CLAIM: {"type":"BELIEF","subject":"self","predicate":"test","strength":-0.5}',
    }
    claims2 = extract_claims_from_event(event2)
    assert claims2[0]["strength"] == 0.0  # Floored at 0.0
