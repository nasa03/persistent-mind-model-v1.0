# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""One-time migration to backfill claim_register events from historical assistant_message events.

This runs exactly once on first boot after upgrade. It scans the entire ledger for
assistant_message events, extracts claims, and emits claim_register events idempotently.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from pmm.core.claim_extractor import extract_claims_from_event


def needs_claim_migration(events: List[Dict[str, Any]]) -> bool:
    """Check if ledger needs claim migration.
    
    Migration is needed if:
    1. There are assistant_message events
    2. There are no claim_register events
    
    Returns True if migration should run.
    """
    has_assistant_messages = any(e.get("kind") == "assistant_message" for e in events)
    has_claim_registers = any(e.get("kind") == "claim_register" for e in events)
    
    # Need migration if we have assistant messages but no claim registers
    return has_assistant_messages and not has_claim_registers


def migrate_claims_from_history(eventlog) -> int:
    """Backfill claim_register events from all historical assistant_message events.
    
    This is a one-time migration that runs on first boot after upgrade.
    It's idempotent - if claim_register events already exist, it skips them.
    
    Args:
        eventlog: EventLog instance
        
    Returns:
        Number of claim_register events emitted
    """
    events = eventlog.read_all()
    
    # Check if migration needed
    if not needs_claim_migration(events):
        return 0
    
    # Build set of existing claim_ids (should be empty on first migration)
    existing_claim_ids = set()
    for ev in events:
        if ev.get("kind") == "claim_register":
            try:
                claim_data = json.loads(ev.get("content", "{}"))
                if isinstance(claim_data, dict):
                    existing_claim_ids.add(claim_data.get("claim_id"))
            except (json.JSONDecodeError, ValueError):
                pass
    
    # Extract claims from all assistant_message events
    claims_to_emit = []
    for ev in events:
        if ev.get("kind") != "assistant_message":
            continue
        
        extracted = extract_claims_from_event(ev)
        for claim in extracted:
            if claim["claim_id"] not in existing_claim_ids:
                claims_to_emit.append(claim)
                existing_claim_ids.add(claim["claim_id"])  # Prevent duplicates within batch
    
    # Emit claim_register events
    emitted_count = 0
    for claim in claims_to_emit:
        claim_content = json.dumps(claim, sort_keys=True, separators=(",", ":"))
        eventlog.append(
            kind="claim_register",
            content=claim_content,
            meta={"source": "claim_migration", "migration_version": "1"},
        )
        emitted_count += 1
    
    return emitted_count
