# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for one-time claim migration from historical assistant_message events."""

import json
import pytest
from pmm.core.event_log import EventLog
from pmm.core.claim_migration import needs_claim_migration, migrate_claims_from_history


def test_needs_migration_empty_ledger():
    """Test that empty ledger doesn't need migration."""
    log = EventLog(":memory:")
    assert needs_claim_migration(log.read_all()) is False


def test_needs_migration_no_assistant_messages():
    """Test that ledger with no assistant messages doesn't need migration."""
    log = EventLog(":memory:")
    log.append(kind="user_message", content="test", meta={})
    assert needs_claim_migration(log.read_all()) is False


def test_needs_migration_with_assistant_no_claims():
    """Test that ledger with assistant messages but no claim_register needs migration."""
    log = EventLog(":memory:")
    log.append(kind="assistant_message", content="BELIEF: test", meta={})
    assert needs_claim_migration(log.read_all()) is True


def test_needs_migration_already_migrated():
    """Test that ledger with claim_register events doesn't need migration."""
    log = EventLog(":memory:")
    log.append(kind="assistant_message", content="BELIEF: test", meta={})
    log.append(kind="claim_register", content="{}", meta={})
    assert needs_claim_migration(log.read_all()) is False


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
