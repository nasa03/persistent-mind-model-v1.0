# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Deterministic Recursive Self-Model rebuilt from structured claim_register events.

Replaces lexical keyword counting with structured claim extraction.
Every belief, value, tendency, and identity statement is now a first-class
claim_register event with deterministic ID, subject/predicate/object structure,
and contradiction detection.

RSM is now a pure materialized view: same ledger → same claims → same RSM.
"""

from __future__ import annotations

from collections import defaultdict
import json
from typing import Any, Dict, Iterable, List, Optional

from .event_log import EventLog
from .concept_metrics import compute_concept_metrics


class RecursiveSelfModel:
    """Deterministic, replay-safe snapshot built from claim_register events.
    
    No more lexical counting. RSM is now a pure aggregation over structured claims.
    """

    def __init__(self, eventlog: Optional[EventLog] = None) -> None:
        self.eventlog = eventlog
        self._last_processed_event_id: Optional[int] = None
        # Claim storage: claim_id -> claim dict
        self._claims: Dict[str, Dict[str, Any]] = {}
        # Aggregated metrics computed from claims
        self.behavioral_tendencies: Dict[str, float] = {}
        self.knowledge_gaps: List[str] = []
        self.interaction_meta_patterns: List[str] = []
        self.reflection_intents: List[str] = []
        self._contradiction_events: List[str] = []
        # Track last snapshot for delta detection
        self._last_snapshot: Optional[Dict[str, Any]] = None

    def reset(self) -> None:
        """Clear all internal state."""
        self._last_processed_event_id = None
        self._claims.clear()
        self.behavioral_tendencies = {}
        self.knowledge_gaps = []
        self.interaction_meta_patterns = []
        self.reflection_intents = []
        self._contradiction_events = []
        self._last_snapshot = None

    def rebuild(self, events: Iterable[Dict[str, Any]]) -> None:
        """Rebuild internal state from the supplied ordered events."""
        self.reset()
        for event in events:
            self.observe(event)
        # After rebuild, compute aggregated metrics
        self._compute_aggregates()

    def observe(self, event: Optional[Dict[str, Any]]) -> None:
        """Process a single event incrementally."""
        if not event:
            return
        
        kind = event.get("kind")
        if kind == "rsm_update":
            return
        
        event_id = event.get("id")
        if isinstance(event_id, int):
            if (
                self._last_processed_event_id is not None
                and event_id <= self._last_processed_event_id
            ):
                return
            self._last_processed_event_id = event_id

        # Process claim_register events
        if kind == "claim_register":
            self._process_claim_event(event)
        
        # Track reflection intents (legacy compatibility)
        elif kind == "reflection":
            content = event.get("content", "")
            try:
                data = json.loads(content)
            except (ValueError, json.JSONDecodeError):
                data = {}
            intent = data.get("intent") if isinstance(data, dict) else None
            if isinstance(intent, str):
                self.reflection_intents.append(intent)
        
        # After each event, recompute aggregates and maybe emit rsm_update
        self._compute_aggregates()
        self._maybe_emit_rsm_update()

    def _process_claim_event(self, event: Dict[str, Any]) -> None:
        """Process a claim_register event and update internal claim storage."""
        content = event.get("content", "")
        try:
            claim = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return
        
        if not isinstance(claim, dict):
            return
        
        claim_id = claim.get("claim_id")
        if not claim_id:
            return
        
        # Store or update claim
        self._claims[claim_id] = claim

    def _compute_aggregates(self) -> None:
        """Compute aggregated metrics from active claims.
        
        This is where we translate structured claims into the legacy
        behavioral_tendencies format for backward compatibility.
        """
        # Count claims by type and predicate
        type_counts: Dict[str, int] = defaultdict(int)
        predicate_counts: Dict[str, int] = defaultdict(int)
        predicate_strengths: Dict[str, float] = defaultdict(float)
        
        active_claims = [
            c for c in self._claims.values() 
            if c.get("status") == "active"
        ]
        
        for claim in active_claims:
            claim_type = claim.get("type", "")
            predicate = claim.get("predicate", "")
            strength = claim.get("strength", 1.0)
            
            if claim_type:
                type_counts[claim_type.lower()] += 1
            
            if predicate:
                predicate_counts[predicate] += 1
                predicate_strengths[predicate] += strength
        
        # Build behavioral tendencies (normalized scores 0-1)
        tendencies: Dict[str, float] = {}
        
        # Map claim types to legacy tendency names
        if type_counts.get("belief", 0) > 0:
            tendencies["belief_count"] = float(type_counts["belief"])
        if type_counts.get("value", 0) > 0:
            tendencies["value_count"] = float(type_counts["value"])
        if type_counts.get("tendency", 0) > 0:
            tendencies["tendency_count"] = float(type_counts["tendency"])
        if type_counts.get("identity", 0) > 0:
            tendencies["identity_count"] = float(type_counts["identity"])
        
        # Extract specific high-value predicates
        # These map to the white-paper's claimed RSM dimensions
        if "is_deterministic" in predicate_counts or "deterministic" in predicate_counts:
            tendencies["determinism_emphasis"] = min(
                1.0,
                (predicate_strengths.get("is_deterministic", 0.0) + 
                 predicate_strengths.get("deterministic", 0.0)) / max(1, len(active_claims))
            )
        
        if "is_replay_centric" in predicate_counts or "replay" in predicate_counts:
            tendencies["replay_centricity"] = min(
                1.0,
                (predicate_strengths.get("is_replay_centric", 0.0) + 
                 predicate_strengths.get("replay", 0.0)) / max(1, len(active_claims))
            )
        
        if "prioritizes_stability" in predicate_counts or "stability" in predicate_counts:
            tendencies["stability_emphasis"] = min(
                1.0,
                (predicate_strengths.get("prioritizes_stability", 0.0) + 
                 predicate_strengths.get("stability", 0.0)) / max(1, len(active_claims))
            )
        
        if "support_aware" in predicate_counts or "support_awareness" in predicate_counts:
            tendencies["support_awareness"] = min(
                1.0,
                (predicate_strengths.get("support_aware", 0.0) + 
                 predicate_strengths.get("support_awareness", 0.0)) / max(1, len(active_claims))
            )
        
        # Total active claim count
        tendencies["active_claim_count"] = float(len(active_claims))
        
        self.behavioral_tendencies = dict(sorted(tendencies.items()))
        
        # Knowledge gaps: extract from claims with "unknown" or "gap" predicates
        gaps = []
        for claim in active_claims:
            predicate = claim.get("predicate", "").lower()
            if "unknown" in predicate or "gap" in predicate:
                obj = claim.get("object")
                if obj and isinstance(obj, str):
                    gaps.append(obj)
        self.knowledge_gaps = sorted(set(gaps))
        
        # Interaction meta-patterns: detect contradictions
        self._detect_contradictions()
        patterns = []
        if self._contradiction_events:
            patterns.append(f"contradictions_detected:{len(self._contradiction_events)}")
        self.interaction_meta_patterns = sorted(patterns)

    def _detect_contradictions(self) -> None:
        """Detect contradictory claims (same subject+predicate, different object)."""
        active_claims = [
            c for c in self._claims.values() 
            if c.get("status") == "active"
        ]
        
        # Group by (subject, predicate)
        groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        for claim in active_claims:
            key = (claim.get("subject"), claim.get("predicate"))
            groups[key].append(claim)
        
        # Find groups with conflicting objects
        contradictions = []
        for key, claims in groups.items():
            if len(claims) > 1:
                objects = set()
                for c in claims:
                    obj = c.get("object")
                    negated = c.get("negated", False)
                    objects.add((obj, negated))
                if len(objects) > 1:
                    # Contradiction detected
                    for c in claims:
                        contradictions.append(c["claim_id"])
        
        self._contradiction_events = sorted(set(contradictions))

    def snapshot(self) -> Dict[str, Any]:
        """Return serialized snapshot for reflections or diagnostics."""
        # Concept-level metrics are derived deterministically from the ledger.
        concept_metrics: Dict[str, Any] = {}
        if self.eventlog is not None:
            try:
                concept_metrics = compute_concept_metrics(self.eventlog)
            except Exception:
                # RSM snapshot must remain robust even if CTL is unused or misconfigured.
                concept_metrics = {}
        
        # Get top tendencies by strength
        top_tendencies = []
        for predicate, strength in sorted(
            self._get_predicate_strengths().items(),
            key=lambda x: (-x[1], x[0])
        )[:10]:
            sources = sum(
                1 for c in self._claims.values()
                if c.get("status") == "active" and c.get("predicate") == predicate
            )
            top_tendencies.append({
                "predicate": predicate,
                "strength": round(strength, 2),
                "sources": sources,
            })
        
        return {
            "behavioral_tendencies": dict(self.behavioral_tendencies),
            "knowledge_gaps": list(self.knowledge_gaps),
            "interaction_meta_patterns": list(self.interaction_meta_patterns),
            "intents": {},  # Legacy compatibility
            "reflections": [{"intent": i} for i in self.reflection_intents],
            "concept_metrics": concept_metrics,
            "active_claim_count": len([c for c in self._claims.values() if c.get("status") == "active"]),
            "contradiction_events": self._contradiction_events,
            "top_tendencies": top_tendencies,
        }

    def _get_predicate_strengths(self) -> Dict[str, float]:
        """Get aggregated strength for each predicate."""
        strengths: Dict[str, float] = defaultdict(float)
        for claim in self._claims.values():
            if claim.get("status") == "active":
                predicate = claim.get("predicate", "")
                strength = claim.get("strength", 1.0)
                if predicate:
                    strengths[predicate] += strength
        return dict(strengths)

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Seed internal state from an existing snapshot.
        
        Note: This is a legacy compatibility method. In the new claim-based RSM,
        we should rebuild from claim_register events instead of loading snapshots.
        """
        self.reset()
        # For backward compatibility, we can reconstruct some state
        tendencies = snapshot.get("behavioral_tendencies") or {}
        if isinstance(tendencies, dict):
            self.behavioral_tendencies = dict(tendencies)
        
        gaps = snapshot.get("knowledge_gaps") or []
        if isinstance(gaps, list):
            self.knowledge_gaps = list(gaps)
        
        imeta = snapshot.get("interaction_meta_patterns") or []
        if isinstance(imeta, list):
            self.interaction_meta_patterns = list(imeta)
        
        refl = snapshot.get("reflections") or []
        if isinstance(refl, list):
            for item in refl:
                if isinstance(item, dict) and isinstance(item.get("intent"), str):
                    self.reflection_intents.append(item["intent"])

    def knowledge_gap_count(self) -> int:
        """Return count of knowledge gaps (legacy compatibility)."""
        return len(self.knowledge_gaps)
    
    def get_claims(self) -> List[Dict[str, Any]]:
        """Return all active claims."""
        return [
            c for c in self._claims.values()
            if c.get("status") == "active"
        ]
    
    def get_claim_by_id(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific claim by ID."""
        return self._claims.get(claim_id)
    
    def _maybe_emit_rsm_update(self) -> None:
        """Emit rsm_update event if snapshot has changed (semantic delta only).
        
        This makes RSM a materialized view with audit trail.
        """
        if self.eventlog is None:
            return
        
        current_snapshot = self.snapshot()
        
        # Skip if no change
        if self._last_snapshot == current_snapshot:
            return
        
        # Emit rsm_update event
        self.eventlog.append(
            kind="rsm_update",
            content=json.dumps(current_snapshot, sort_keys=True, separators=(",", ":")),
            meta={"source": "rsm"},
        )
        
        # Update last snapshot
        self._last_snapshot = current_snapshot
