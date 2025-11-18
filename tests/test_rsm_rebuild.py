# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for RSM rebuild from claim_register events - replay equivalence."""

import json
import pytest
from pmm.core.event_log import EventLog
from pmm.core.rsm import RecursiveSelfModel
from pmm.core.mirror import Mirror


def test_rsm_rebuild_from_claim_register_events():
    """Test that RSM rebuilds correctly from claim_register events."""
    log = EventLog(":memory:")
    
    # Simulate assistant_message with claims
    log.append(
        kind="assistant_message",
        content="BELIEF: I am deterministic\nVALUE: Stability over novelty",
        meta={"role": "assistant"},
    )
    
    # Manually add claim_register events (normally done by loop.py)
    claim1 = {
        "claim_id": "test_claim_1",
        "source_event_id": 1,
        "type": "BELIEF",
        "subject": "self",
        "predicate": "is_deterministic",
        "object": "always",
        "raw_text": "BELIEF: I am deterministic",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim1, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    
    claim2 = {
        "claim_id": "test_claim_2",
        "source_event_id": 1,
        "type": "VALUE",
        "subject": "self",
        "predicate": "prioritizes",
        "object": "stability",
        "raw_text": "VALUE: Stability over novelty",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim2, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    
    # Build RSM
    rsm = RecursiveSelfModel(eventlog=log)
    rsm.rebuild(log.read_all())
    
    # Verify claims were loaded
    claims = rsm.get_claims()
    assert len(claims) == 2
    
    # Verify snapshot contains expected data
    snapshot = rsm.snapshot()
    assert snapshot["active_claim_count"] == 2
    assert "belief_count" in snapshot["behavioral_tendencies"]
    assert "value_count" in snapshot["behavioral_tendencies"]


def test_rsm_replay_equivalence():
    """Test that rebuilding RSM twice produces identical results."""
    log = EventLog(":memory:")
    
    # Add claims
    for i in range(5):
        claim = {
            "claim_id": f"claim_{i}",
            "source_event_id": i + 1,
            "type": "BELIEF",
            "subject": "self",
            "predicate": f"predicate_{i}",
            "object": f"object_{i}",
            "raw_text": f"BELIEF: test {i}",
            "negated": False,
            "strength": 1.0,
            "status": "active",
        }
        log.append(
            kind="claim_register",
            content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
            meta={"source": "claim_extractor"},
        )
    
    # Build RSM first time
    rsm1 = RecursiveSelfModel(eventlog=log)
    rsm1.rebuild(log.read_all())
    snapshot1 = rsm1.snapshot()
    
    # Build RSM second time
    rsm2 = RecursiveSelfModel(eventlog=log)
    rsm2.rebuild(log.read_all())
    snapshot2 = rsm2.snapshot()
    
    # Snapshots should be identical
    assert snapshot1["active_claim_count"] == snapshot2["active_claim_count"]
    assert snapshot1["behavioral_tendencies"] == snapshot2["behavioral_tendencies"]
    assert snapshot1["knowledge_gaps"] == snapshot2["knowledge_gaps"]
    assert snapshot1["contradiction_events"] == snapshot2["contradiction_events"]


def test_rsm_contradiction_detection():
    """Test that RSM detects contradictory claims."""
    log = EventLog(":memory:")
    
    # Add two contradictory claims
    claim1 = {
        "claim_id": "claim_1",
        "source_event_id": 1,
        "type": "BELIEF",
        "subject": "self",
        "predicate": "prioritizes",
        "object": "stability",
        "raw_text": "BELIEF: I prioritize stability",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim1, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    
    claim2 = {
        "claim_id": "claim_2",
        "source_event_id": 2,
        "type": "BELIEF",
        "subject": "self",
        "predicate": "prioritizes",
        "object": "novelty",  # Contradicts claim1
        "raw_text": "BELIEF: I prioritize novelty",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim2, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    
    # Build RSM
    rsm = RecursiveSelfModel(eventlog=log)
    rsm.rebuild(log.read_all())
    
    # Verify contradiction detected
    snapshot = rsm.snapshot()
    assert len(snapshot["contradiction_events"]) == 2
    assert "claim_1" in snapshot["contradiction_events"]
    assert "claim_2" in snapshot["contradiction_events"]


def test_rsm_incremental_observe():
    """Test that RSM can observe events incrementally."""
    log = EventLog(":memory:")
    rsm = RecursiveSelfModel(eventlog=log)
    
    # Add claims one by one
    for i in range(3):
        claim = {
            "claim_id": f"claim_{i}",
            "source_event_id": i + 1,
            "type": "BELIEF",
            "subject": "self",
            "predicate": f"pred_{i}",
            "object": f"obj_{i}",
            "raw_text": f"BELIEF: test {i}",
            "negated": False,
            "strength": 1.0,
            "status": "active",
        }
        event_id = log.append(
            kind="claim_register",
            content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
            meta={"source": "claim_extractor"},
        )
        
        # Observe incrementally
        event = log.get(event_id)
        rsm.observe(event)
    
    # Verify all claims loaded
    assert len(rsm.get_claims()) == 3


def test_rsm_with_mirror_integration():
    """Test RSM integration with Mirror projection."""
    log = EventLog(":memory:")
    mirror = Mirror(log, enable_rsm=True, listen=True, auto_rebuild=False)
    
    # Add claim_register event
    claim = {
        "claim_id": "test_claim",
        "source_event_id": 1,
        "type": "BELIEF",
        "subject": "self",
        "predicate": "is_deterministic",
        "object": "always",
        "raw_text": "BELIEF: I am deterministic",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    
    # Rebuild mirror (which rebuilds RSM)
    mirror.rebuild()
    
    # Verify claims accessible through mirror
    claims = mirror.get_claims()
    assert len(claims) == 1
    assert claims[0]["claim_id"] == "test_claim"
    
    # Verify get_claim_by_id works
    retrieved = mirror.get_claim_by_id("test_claim")
    assert retrieved is not None
    assert retrieved["predicate"] == "is_deterministic"


def test_rsm_behavioral_tendencies_computed():
    """Test that behavioral tendencies are computed from claims."""
    log = EventLog(":memory:")
    
    # Add multiple belief claims
    for i in range(5):
        claim = {
            "claim_id": f"belief_{i}",
            "source_event_id": i + 1,
            "type": "BELIEF",
            "subject": "self",
            "predicate": f"pred_{i}",
            "object": f"obj_{i}",
            "raw_text": f"BELIEF: test {i}",
            "negated": False,
            "strength": 1.0,
            "status": "active",
        }
        log.append(
            kind="claim_register",
            content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
            meta={"source": "claim_extractor"},
        )
    
    # Add value claims
    for i in range(3):
        claim = {
            "claim_id": f"value_{i}",
            "source_event_id": i + 10,
            "type": "VALUE",
            "subject": "self",
            "predicate": f"values_{i}",
            "object": f"obj_{i}",
            "raw_text": f"VALUE: test {i}",
            "negated": False,
            "strength": 1.0,
            "status": "active",
        }
        log.append(
            kind="claim_register",
            content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
            meta={"source": "claim_extractor"},
        )
    
    rsm = RecursiveSelfModel(eventlog=log)
    rsm.rebuild(log.read_all())
    
    snapshot = rsm.snapshot()
    tendencies = snapshot["behavioral_tendencies"]
    
    # Verify counts
    assert tendencies.get("belief_count") == 5.0
    assert tendencies.get("value_count") == 3.0
    assert tendencies.get("active_claim_count") == 8.0


def test_rsm_ignores_rsm_update_events():
    """Test that RSM ignores rsm_update events to avoid recursion."""
    log = EventLog(":memory:")
    
    # Add a claim
    claim = {
        "claim_id": "test_claim",
        "source_event_id": 1,
        "type": "BELIEF",
        "subject": "self",
        "predicate": "test",
        "object": "value",
        "raw_text": "BELIEF: test",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    
    # Add an rsm_update event (should be ignored)
    log.append(
        kind="rsm_update",
        content=json.dumps({"test": "data"}),
        meta={},
    )
    
    rsm = RecursiveSelfModel(eventlog=log)
    rsm.rebuild(log.read_all())
    
    # Should only have 1 claim (rsm_update ignored)
    assert len(rsm.get_claims()) == 1


def test_rsm_top_tendencies_in_snapshot():
    """Test that snapshot includes top_tendencies."""
    log = EventLog(":memory:")
    
    # Add claims with specific predicates
    predicates = ["is_deterministic", "is_deterministic", "prioritizes_stability"]
    for i, pred in enumerate(predicates):
        claim = {
            "claim_id": f"claim_{i}",
            "source_event_id": i + 1,
            "type": "BELIEF",
            "subject": "self",
            "predicate": pred,
            "object": "test",
            "raw_text": f"BELIEF: {pred}",
            "negated": False,
            "strength": 1.0,
            "status": "active",
        }
        log.append(
            kind="claim_register",
            content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
            meta={"source": "claim_extractor"},
        )
    
    rsm = RecursiveSelfModel(eventlog=log)
    rsm.rebuild(log.read_all())
    
    snapshot = rsm.snapshot()
    top_tendencies = snapshot["top_tendencies"]
    
    # Should have top tendencies sorted by strength
    assert len(top_tendencies) > 0
    # is_deterministic should be top (2 sources)
    assert top_tendencies[0]["predicate"] == "is_deterministic"
    assert top_tendencies[0]["sources"] == 2


def test_rsm_emits_rsm_update_on_delta():
    """Test that RSM emits rsm_update events when snapshot changes."""
    log = EventLog(":memory:")
    rsm = RecursiveSelfModel(eventlog=log)
    
    # Initial state - no rsm_update yet
    events = log.read_all()
    assert len([e for e in events if e["kind"] == "rsm_update"]) == 0
    
    # Add first claim - should trigger rsm_update
    claim1 = {
        "claim_id": "claim_1",
        "source_event_id": 1,
        "type": "BELIEF",
        "subject": "self",
        "predicate": "test",
        "object": "value",
        "raw_text": "BELIEF: test",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim1, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    
    # Observe the claim
    rsm.observe(log.get(1))
    
    # Should have emitted rsm_update
    events = log.read_all()
    rsm_updates = [e for e in events if e["kind"] == "rsm_update"]
    assert len(rsm_updates) == 1
    
    # Add another claim - should trigger another rsm_update
    claim2 = {
        "claim_id": "claim_2",
        "source_event_id": 3,
        "type": "VALUE",
        "subject": "self",
        "predicate": "test2",
        "object": "value2",
        "raw_text": "VALUE: test2",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim2, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    rsm.observe(log.get(3))
    
    # Should have 2 rsm_update events now
    events = log.read_all()
    rsm_updates = [e for e in events if e["kind"] == "rsm_update"]
    assert len(rsm_updates) == 2


def test_rsm_update_not_emitted_on_no_delta():
    """Test that RSM doesn't emit rsm_update if snapshot hasn't changed."""
    log = EventLog(":memory:")
    rsm = RecursiveSelfModel(eventlog=log)
    
    # Add a claim
    claim = {
        "claim_id": "claim_1",
        "source_event_id": 1,
        "type": "BELIEF",
        "subject": "self",
        "predicate": "test",
        "object": "value",
        "raw_text": "BELIEF: test",
        "negated": False,
        "strength": 1.0,
        "status": "active",
    }
    log.append(
        kind="claim_register",
        content=json.dumps(claim, sort_keys=True, separators=(",", ":")),
        meta={"source": "claim_extractor"},
    )
    rsm.observe(log.get(1))
    
    # Count rsm_update events
    events = log.read_all()
    rsm_updates_before = len([e for e in events if e["kind"] == "rsm_update"])
    
    # Add a non-claim event (should not change RSM)
    log.append(kind="user_message", content="test", meta={})
    rsm.observe(log.get(3))
    
    # Should not have emitted another rsm_update
    events = log.read_all()
    rsm_updates_after = len([e for e in events if e["kind"] == "rsm_update"])
    assert rsm_updates_before == rsm_updates_after
