# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Always-correct claim migration from historical assistant_message events.

This runs on every boot and scans the entire ledger for assistant_message events.
It emits claim_register events only for claims that don't already exist (by claim_id).

This is O(n) on boot but guarantees correctness:
- Partial migrations complete automatically
- Aborted runs recover on next boot
- No "run once and pray" fragility
"""

from __future__ import annotations

import json

from pmm.core.claim_extractor import extract_claims_from_event


def migrate_claims_from_history(eventlog, force: bool = False) -> int:
    """Backfill claim_register events from all historical assistant_message events.

    Always scans the entire ledger on every boot. Emits claim_register events only
    for claims that don't already exist (by claim_id). This guarantees correctness
    even for partial migrations, aborted runs, or corrupted state.

    Args:
        eventlog: EventLog instance
        force: If True, forces a full rescan even if migration seems complete

    Returns:
        Number of claim_register events emitted
    """
    events = eventlog.read_all()

    # Build set of existing claim_ids
    existing_claim_ids = set()
    for ev in events:
        if ev.get("kind") == "claim_register":
            try:
                claim_data = json.loads(ev.get("content", "{}"))
                if isinstance(claim_data, dict):
                    claim_id = claim_data.get("claim_id")
                    if claim_id:
                        existing_claim_ids.add(claim_id)
            except (json.JSONDecodeError, ValueError):
                pass

    # Extract claims from all assistant_message events
    claims_to_emit = []
    for ev in events:
        if ev.get("kind") != "assistant_message":
            continue

        extracted = extract_claims_from_event(ev)
        for claim in extracted:
            claim_id = claim["claim_id"]
            if claim_id not in existing_claim_ids:
                claims_to_emit.append(claim)
                existing_claim_ids.add(claim_id)  # Prevent duplicates within batch

    # Emit claim_register events
    emitted_count = 0
    for claim in claims_to_emit:
        claim_content = json.dumps(claim, sort_keys=True, separators=(",", ":"))
        eventlog.append(
            kind="claim_register",
            content=claim_content,
            meta={
                "source": "claim_migration",
                "migration_version": "1",
                "force": force,
            },
        )
        emitted_count += 1

    return emitted_count
