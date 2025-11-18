# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Deterministic structured claim extraction from assistant_message events.

Extracts BELIEF:, VALUE:, TENDENCY:, IDENTITY:, CLAIM: lines into structured
claim_register events. Pure function, no state, no randomness, no model calls.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from blake3 import blake3


CLAIM_PREFIXES = {
    "CLAIM:": "CLAIM",
    "BELIEF:": "BELIEF",
    "VALUE:": "VALUE",
    "TENDENCY:": "TENDENCY",
    "IDENTITY:": "IDENTITY",
    "ONTOLOGY:": "ONTOLOGY",
}


def extract_claims_from_event(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract structured claims from an assistant_message event.

    Returns a list of claim dictionaries ready to be emitted as claim_register events.
    Each claim has a deterministic claim_id based on blake3(event_id:raw_text).

    Args:
        event: Event dictionary with 'id', 'content', 'kind' fields

    Returns:
        List of claim dictionaries, empty if no claims found or wrong event kind
    """
    if event.get("kind") != "assistant_message":
        return []

    event_id = event.get("id")
    if not isinstance(event_id, int):
        return []

    content = event.get("content", "")
    if not isinstance(content, str):
        return []

    lines = [line.strip() for line in content.split("\n") if line.strip()]
    claims = []

    for line in lines:
        claim = _parse_claim_line(line, event_id)
        if claim:
            claims.append(claim)

    return claims


def _parse_claim_line(line: str, source_event_id: int) -> Optional[Dict[str, Any]]:
    """Parse a single line into a structured claim.

    Handles both simple format:
        BELIEF: I am replay-centric

    And structured JSON format:
        CLAIM: {"type":"BELIEF","subject":"self","predicate":"is","object":"replay-centric"}

    Returns None if line doesn't match any claim prefix.
    """
    # Check for claim prefix
    claim_type = None
    remainder = None

    for prefix, ctype in CLAIM_PREFIXES.items():
        if line.startswith(prefix):
            claim_type = ctype
            remainder = line[len(prefix) :].strip()
            break

    if not claim_type or not remainder:
        return None

    # Try parsing as JSON first (structured format)
    if remainder.startswith("{"):
        try:
            parsed = json.loads(remainder)
            if isinstance(parsed, dict):
                return _build_claim_from_json(parsed, line, source_event_id, claim_type)
        except (json.JSONDecodeError, ValueError):
            pass  # Fall through to simple parsing

    # Simple format: just text after prefix
    return _build_claim_from_text(remainder, line, source_event_id, claim_type)


def _build_claim_from_json(
    parsed: Dict[str, Any], raw_text: str, source_event_id: int, default_type: str
) -> Dict[str, Any]:
    """Build claim from structured JSON format."""
    claim_type = parsed.get("type", default_type)
    subject = parsed.get("subject", "self")
    predicate = parsed.get("predicate", "")
    obj = parsed.get("object")
    negated = parsed.get("negated", False)
    strength = parsed.get("strength", 1.0)

    # Ensure strength is float in [0, 1]
    try:
        strength = float(strength)
        if strength < 0:
            strength = 0.0
        elif strength > 1.0:
            strength = 1.0
    except (TypeError, ValueError):
        strength = 1.0

    claim_id = _generate_claim_id(source_event_id, raw_text)

    return {
        "claim_id": claim_id,
        "source_event_id": source_event_id,
        "type": claim_type,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "raw_text": raw_text,
        "negated": bool(negated),
        "strength": strength,
        "status": "active",
    }


def _build_claim_from_text(
    text: str, raw_text: str, source_event_id: int, claim_type: str
) -> Dict[str, Any]:
    """Build claim from simple text format.

    Simple format is DEPRECATED. We only accept structured JSON.
    This function exists for backward compatibility but returns minimal structure.

    The text is stored as-is in raw_text. No keyword parsing, no heuristics.
    If you want structured claims, use JSON format:
    CLAIM: {"type":"BELIEF","subject":"self","predicate":"X","object":"Y"}
    """
    claim_id = _generate_claim_id(source_event_id, raw_text)

    # No keyword parsing. Store raw text only.
    # Subject defaults to "self", predicate is the raw text, no object.
    return {
        "claim_id": claim_id,
        "source_event_id": source_event_id,
        "type": claim_type,
        "subject": "self",
        "predicate": text,  # Raw text as predicate, no parsing
        "object": None,
        "raw_text": raw_text,
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }


def _generate_claim_id(source_event_id: int, raw_text: str) -> str:
    """Generate deterministic claim_id using BLAKE3.

    Format: blake3(f"{event_id}:{raw_text}")[:16] (first 16 hex chars = 64 bits)
    """
    payload = f"{source_event_id}:{raw_text}"
    h = blake3(payload.encode("utf-8"))
    return h.hexdigest()[:16]


def detect_contradictions(
    claims: List[Dict[str, Any]], new_claim: Dict[str, Any]
) -> List[str]:
    """Detect if new_claim contradicts any existing active claims.

    A contradiction occurs when:
    - Same subject and predicate
    - Different object or negation

    Returns list of contradicted claim_ids.
    """
    contradictions = []

    new_subject = new_claim.get("subject")
    new_predicate = new_claim.get("predicate")
    new_object = new_claim.get("object")
    new_negated = new_claim.get("negated", False)

    if not new_subject or not new_predicate:
        return []

    for claim in claims:
        if claim.get("status") != "active":
            continue

        # Same subject and predicate?
        if (
            claim.get("subject") == new_subject
            and claim.get("predicate") == new_predicate
        ):

            # Different object or negation?
            if (
                claim.get("object") != new_object
                or claim.get("negated", False) != new_negated
            ):
                contradictions.append(claim["claim_id"])

    return contradictions
