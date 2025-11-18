# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for one-time claim migration from historical assistant_message events."""

import json
import pytest
from pmm.core.event_log import EventLog
from pmm.core.claim_migration import migrate_claims_from_history


def test_migrate_claims_from_history():
    """Test that migration backfills claim_register events."""
    log = EventLog(":memory:")
    
    # Add historical assistant messages with claims
    log.append(kind="assistant_message", content="BELIEF: I am deterministic", meta={})
    log.append(kind="assistant_message", content="VALUE: Stability is paramount", meta={})
    log.append(kind="assistant_message", content="No claims here", meta={})
    
    # Run migration
    count = migrate_claims_from_history(log)
    
    # Should have emitted 2 claim_register events
    assert count == 2
    
    # Verify claim_register events exist
    events = log.read_all()
    claim_events = [e for e in events if e.get("kind") == "claim_register"]
    assert len(claim_events) == 2
    
    # Verify claim content
    claim1 = json.loads(claim_events[0]["content"])
    assert claim1["type"] == "BELIEF"
    assert claim1["source_event_id"] == 1
    
    claim2 = json.loads(claim_events[1]["content"])
    assert claim2["type"] == "VALUE"
    assert claim2["source_event_id"] == 2


def test_migrate_claims_idempotent():
    """Test that migration is idempotent - running twice doesn't duplicate."""
    log = EventLog(":memory:")
    log.append(kind="assistant_message", content="BELIEF: test", meta={})
    
    # Run migration twice
    count1 = migrate_claims_from_history(log)
    count2 = migrate_claims_from_history(log)
    
    # First run emits, second run skips (already has claim_register)
    assert count1 == 1
    assert count2 == 0
    
    # Only one claim_register event
    events = log.read_all()
    claim_events = [e for e in events if e.get("kind") == "claim_register"]
    assert len(claim_events) == 1


def test_migrate_claims_skips_non_assistant():
    """Test that migration only processes assistant_message events."""
    log = EventLog(":memory:")
    log.append(kind="user_message", content="BELIEF: user belief", meta={})
    log.append(kind="reflection", content="BELIEF: reflection belief", meta={})
    log.append(kind="assistant_message", content="BELIEF: assistant belief", meta={})
    
    count = migrate_claims_from_history(log)
    
    # Only assistant_message should be processed
    assert count == 1
    
    events = log.read_all()
    claim_events = [e for e in events if e.get("kind") == "claim_register"]
    assert len(claim_events) == 1
    
    claim = json.loads(claim_events[0]["content"])
    assert claim["source_event_id"] == 3  # The assistant_message


def test_migrate_claims_multiple_claims_per_message():
    """Test migration with multiple claims in one message."""
    log = EventLog(":memory:")
    log.append(
        kind="assistant_message",
        content="BELIEF: I am deterministic\nVALUE: Stability\nTENDENCY: Avoid randomness",
        meta={},
    )
    
    count = migrate_claims_from_history(log)
    
    # Should emit 3 claim_register events
    assert count == 3
    
    events = log.read_all()
    claim_events = [e for e in events if e.get("kind") == "claim_register"]
    assert len(claim_events) == 3


def test_migrate_claims_preserves_claim_ids():
    """Test that migration produces deterministic claim_ids."""
    log1 = EventLog(":memory:")
    log1.append(kind="assistant_message", content="BELIEF: test", meta={})
    migrate_claims_from_history(log1)
    
    log2 = EventLog(":memory:")
    log2.append(kind="assistant_message", content="BELIEF: test", meta={})
    migrate_claims_from_history(log2)
    
    # Same input should produce same claim_id
    events1 = log1.read_all()
    events2 = log2.read_all()
    
    claim1 = json.loads([e for e in events1 if e["kind"] == "claim_register"][0]["content"])
    claim2 = json.loads([e for e in events2 if e["kind"] == "claim_register"][0]["content"])
    
    assert claim1["claim_id"] == claim2["claim_id"]


def test_migrate_claims_meta_tags():
    """Test that migrated claims have correct meta tags."""
    log = EventLog(":memory:")
    log.append(kind="assistant_message", content="BELIEF: test", meta={})
    
    migrate_claims_from_history(log)
    
    events = log.read_all()
    claim_event = [e for e in events if e["kind"] == "claim_register"][0]
    
    # Check meta tags
    assert claim_event["meta"]["source"] == "claim_migration"
    assert claim_event["meta"]["migration_version"] == "1"


def test_migrate_50_events_idempotent_with_partial_corruption():
    """Test migration with 50 historical events, partial corruption, and idempotency.
    
    This is the critical test that verifies:
    1. Large ledger migration works
    2. Partial migrations complete on reboot
    3. Duplicate injection doesn't break idempotency
    4. Always exactly the right number of claims
    """
    log = EventLog(":memory:")
    
    # Add 50 historical assistant_message events with claims
    for i in range(50):
        log.append(
            kind="assistant_message",
            content=f"BELIEF: claim number {i}",
            meta={},
        )
    
    # First boot - should emit 50 claim_register events
    count1 = migrate_claims_from_history(log)
    assert count1 == 50
    
    events = log.read_all()
    claim_events = [e for e in events if e["kind"] == "claim_register"]
    assert len(claim_events) == 50
    
    # Kill and reboot - should emit 0 new events (idempotent)
    count2 = migrate_claims_from_history(log)
    assert count2 == 0
    
    events = log.read_all()
    claim_events = [e for e in events if e["kind"] == "claim_register"]
    assert len(claim_events) == 50  # Still exactly 50
    
    # Simulate corruption: manually inject a duplicate claim_register mid-ledger
    # This simulates a partial migration or corrupted state
    duplicate_claim = json.loads(claim_events[25]["content"])
    log.append(
        kind="claim_register",
        content=json.dumps(duplicate_claim, sort_keys=True, separators=(",", ":")),
        meta={"source": "manual_corruption"},
    )
    
    # Reboot again - should still emit 0 new events (duplicate detected)
    count3 = migrate_claims_from_history(log)
    assert count3 == 0
    
    # Should have 51 claim_register events total (50 + 1 duplicate)
    # But migration correctly skips the duplicate
    events = log.read_all()
    claim_events = [e for e in events if e["kind"] == "claim_register"]
    assert len(claim_events) == 51
    
    # Verify all 50 unique claim_ids are present
    claim_ids = set()
    for ev in claim_events:
        claim_data = json.loads(ev["content"])
        claim_ids.add(claim_data["claim_id"])
    assert len(claim_ids) == 50  # Exactly 50 unique claims


def test_migrate_empty_ledger_is_noop():
    """Test that migration on empty ledger is a no-op."""
    log = EventLog(":memory:")
    count = migrate_claims_from_history(log)
    assert count == 0
    assert len(log.read_all()) == 0


def test_migrate_force_flag():
    """Test that force flag is recorded in meta."""
    log = EventLog(":memory:")
    log.append(kind="assistant_message", content="BELIEF: test", meta={})
    
    # First migration without force
    migrate_claims_from_history(log, force=False)
    events = log.read_all()
    claim_event = [e for e in events if e["kind"] == "claim_register"][0]
    assert claim_event["meta"]["force"] is False
    
    # Clear and try with force
    log2 = EventLog(":memory:")
    log2.append(kind="assistant_message", content="BELIEF: test2", meta={})
    migrate_claims_from_history(log2, force=True)
    events2 = log2.read_all()
    claim_event2 = [e for e in events2 if e["kind"] == "claim_register"][0]
    assert claim_event2["meta"]["force"] is True
