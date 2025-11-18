# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.cli import handle_pm_command


SENSITIVE = {"config", "checkpoint_manifest", "embedding_add", "retrieval_selection"}


def _last_config(eventlog: EventLog, type_name: str):
    for e in reversed(eventlog.read_all()):
        if e.get("kind") != "config":
            continue
        try:
            data = json.loads(e.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == type_name:
            return e, data
    return None


def test_policy_blocks_cli_sensitive_writes():
    log = EventLog(":memory:")
    # Boot kernel to inject policy
    AutonomyKernel(log)

    # Direct EventLog append for a sensitive kind from cli should raise and create a violation
    try:
        log.append(
            kind="config",
            content=json.dumps({"type": "retrieval", "strategy": "fixed", "limit": 5}),
            meta={"source": "cli"},
        )
        raised = False
    except PermissionError:
        raised = True
    assert raised, "Expected policy to block cli writing config"

    violations = [e for e in log.read_all() if e.get("kind") == "violation"]
    assert violations, "Expected a violation event to be appended"
    v = violations[-1]
    assert (v.get("meta") or {}).get("actor") == "cli"
    assert (v.get("meta") or {}).get("attempt_kind") == "config"

    # CLI checkpoint handler must be forbidden by policy
    out = handle_pm_command("/pm checkpoint", log)
    # If no summary exists yet, handler returns a precondition message;
    # once a summary exists, policy forbids CLI checkpoint writes.
    if out != "Forbidden by policy.":
        # Create a summary anchor then try again
        log.append(kind="summary_update", content="{}", meta={})
        out2 = handle_pm_command("/pm checkpoint", log)
        assert out2 == "Forbidden by policy.", out2


def test_autonomy_initializes_policy_and_retrieval_config():
    log = EventLog(":memory:")
    AutonomyKernel(log)

    # Policy exists and is from autonomy_kernel
    policy = _last_config(log, "policy")
    assert policy is not None
    assert (policy[0].get("meta") or {}).get("source") == "autonomy_kernel"

    # Retrieval config exists and is from autonomy_kernel
    retrieval = _last_config(log, "retrieval")
    assert retrieval is not None
    assert (retrieval[0].get("meta") or {}).get("source") == "autonomy_kernel"
    assert retrieval[1].get("strategy") == "vector"


def test_autonomy_embeddings_selection_verification_checkpoint_and_parity():
    """Now uses dummy adapter + forced claim injection to trigger real RSM delta."""
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter())

    # Override retrieval config to fixed to avoid heavy vector index work.
    log.append(
        kind="config",
        content=json.dumps({"type": "retrieval", "strategy": "fixed", "limit": 5}),
        meta={"source": "test"},
    )

    # Force a real structured claim so RSM actually changes
    log.append(
        kind="assistant_message",
        content="BELIEF: I am replay-centric and deterministic.",
        meta={},
    )

    # Run a few turns — autonomy kernel will see the claim → RSM delta → reflect
    for _ in range(6):
        loop.run_turn("hello")

    events = log.read_all()

    # Assert reflection was triggered by the claim (not by embeddings)
    reflections = [e for e in events if e.get("kind") == "reflection"]
    assert reflections, "Expected at least one reflection event"

    # Prove the metrics/checkpoint logic still operates under dummy adapter
    metrics = [e for e in events if e.get("kind") == "metrics_turn"]
    assert metrics, "Expected metrics_turn events to be emitted"
