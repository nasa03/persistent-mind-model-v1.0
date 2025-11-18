# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/ctl_projection.py
"""Helpers for rebuilding CTL from Mirror and MemeGraph projections.

This module provides a projection-driven path for keeping the ConceptGraph
in sync with higher-level projections instead of reading directly from
EventLog. It is intentionally minimal and deterministic:

- Mirror is responsible for producing concept nodes (ConceptSnapshot).
- MemeGraph is responsible for lifting event-level structure to concept edges.
- ConceptGraph consumes both via rebuild_from_projections().
"""

from __future__ import annotations

from typing import Dict, List

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.meme_graph import get_concept_edges
from pmm.core.concept_graph import ConceptGraph


def rebuild_ctl_from_projections(
    eventlog: EventLog, concept_graph: ConceptGraph
) -> None:
    """Rebuild ConceptGraph from Mirror + MemeGraph projections.

    This is a pure projection path:
    - Mirror defines the current concept nodes.
    - MemeGraph plus a lightweight binding map define the concept edges.

    The binding map here is minimal by design, focusing first on commitments:
    - For each open commitment, bind the commitment_open event to a
      ConceptId of the form "commitment:<cid>".
    """
    mirror = Mirror(eventlog, enable_rsm=False, listen=False)
    snapshots = mirror.get_concept_snapshots()

    # Build a richer event->ConceptId binding map spanning:
    # - commitments (open)
    # - reflection sources
    # - stability / coherence metrics
    # - summary / identity state
    bindings: Dict[int, List[str]] = {}

    # Commitments: bind commitment_open events to commitment:<cid> concepts.
    for cid, data in mirror.open_commitments.items():
        try:
            event_id = int(data["event_id"])
        except Exception:
            continue
        bindings.setdefault(event_id, []).append(f"commitment:{cid}")

    # Metrics, summaries, and reflections: bind directly by event kind.
    events = eventlog.read_all()
    for ev in events:
        kind = ev.get("kind")
        try:
            eid = int(ev.get("id", 0))
        except Exception:
            continue
        if kind == "stability_metrics":
            bindings.setdefault(eid, []).append("metric:stability_score")
        elif kind == "coherence_check":
            bindings.setdefault(eid, []).append("metric:coherence_score")
        elif kind == "summary_update":
            bindings.setdefault(eid, []).append("topic:summary_state")
        elif kind == "reflection":
            meta = ev.get("meta") or {}
            source = meta.get("source", "user")
            bindings.setdefault(eid, []).append(f"reflection_source:{source}")

    edges = get_concept_edges(eventlog=eventlog, concept_bindings=bindings)

    # Use last_event_id as a monotonic projection version anchor.
    projection_version = int(mirror.last_event_id or 0)
    concept_graph.rebuild_from_projections(
        concepts=snapshots,
        edges=edges,
        projection_version=projection_version,
    )
