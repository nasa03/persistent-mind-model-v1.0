# RSM Migration: Lexical Counting → Structured Claims

## Summary

The RSM (Recursive Self-Model) has been completely rewritten to use structured `claim_register` events instead of lexical keyword counting. This is a **fidelity fix** that makes the runtime match what the white-paper already claims Echo is doing.

## What Changed

### Before (Lexical Counting - REMOVED)
- RSM counted keywords like "determinism", "stability", "adaptability" in message text
- Counters were capped at 50 to prevent unbounded growth
- No structured representation of beliefs, values, or tendencies
- No way to track contradictions or revisions

### After (Structured Claims - NEW)
- Every `BELIEF:`, `VALUE:`, `TENDENCY:`, `IDENTITY:` line is extracted as a structured claim
- Each claim has: `claim_id`, `subject`, `predicate`, `object`, `strength`, `status`
- Claims are deterministic: same event → same claim_id (blake2b hash)
- RSM is now a pure materialized view: same ledger → same claims → same RSM
- Contradiction detection built-in
- Full traceability: every claim points to source event

## Breaking Changes

### Tests That Need Updates

The following tests in `pmm/tests/test_mirror_rsm.py` test the **old lexical counting behavior** and will fail:

- `test_rsm_detects_identity_pattern` - expects `identity_query` count
- `test_rsm_counts_knowledge_gaps_deterministically` - expects lexical gap detection
- `test_rsm_counts_stability_and_adaptability_occurrences` - expects keyword counts
- `test_rsm_caps_stability_adaptability_at_50` - expects capping behavior
- `test_rsm_instantiation_capacity_counts_and_caps` - expects keyword counts
- `test_rsm_uniqueness_emphasis_score_from_hash_prefixes` - expects uniqueness score

These tests should be **rewritten** to test claim extraction, not keyword counting.

### API Compatibility

The RSM API is **preserved**:
- `rsm.snapshot()` still returns `behavioral_tendencies`, `knowledge_gaps`, etc.
- `rsm.rebuild(events)` still works
- `rsm.observe(event)` still works

But the **content** of these structures is now computed from claims, not keywords.

## Migration Path for Existing Ledgers

When you run the new code on an existing ledger:

1. **First run**: The claim extractor will process all historical `assistant_message` events
2. **Claim emission**: Hundreds of `claim_register` events will be appended (one per historical claim line)
3. **RSM rebuild**: RSM will rebuild from these new `claim_register` events
4. **Going forward**: Only new claims are emitted (idempotent check via `claim_id`)

This is **correct and expected** behavior. The ledger is growing to include structured data that was previously implicit.

## New Event Kind

```json
{
  "kind": "claim_register",
  "content": "{\"claim_id\":\"abc123\",\"source_event_id\":42,\"type\":\"BELIEF\",\"subject\":\"self\",\"predicate\":\"is_deterministic\",\"object\":\"always\",\"raw_text\":\"BELIEF: I am deterministic\",\"negated\":false,\"strength\":1.0,\"status\":\"active\"}",
  "meta": {"source": "claim_extractor"}
}
```

## Testing

New tests verify:
- ✅ Deterministic claim extraction (`tests/test_claim_extractor.py`)
- ✅ RSM rebuild from claims (`tests/test_rsm_rebuild.py`)
- ✅ Replay equivalence (same ledger → same claims)
- ✅ Contradiction detection
- ✅ Idempotency (no duplicate claims)

## Benefits

1. **No hallucination**: Every claim is traceable to an exact ledger event
2. **Contradiction detection**: Automatic detection of conflicting beliefs
3. **Structured queries**: Can ask "What are my beliefs about X?" with precision
4. **Revision tracking**: Claims can be marked `revised` or `contradicted`
5. **No regex**: Pure structured parsing, no brittle keyword matching
6. **Deterministic**: blake2b hashing ensures replay equivalence

## Example

### Old System (Lexical)
```
assistant_message: "I prioritize determinism and stability."
→ RSM: determinism_emphasis += 2, stability_emphasis += 1
```

### New System (Structured)
```
assistant_message: "BELIEF: I prioritize determinism\nVALUE: Stability is paramount"
→ claim_register: {claim_id: "abc123", type: "BELIEF", predicate: "prioritizes", object: "determinism"}
→ claim_register: {claim_id: "def456", type: "VALUE", predicate: "is_paramount", object: "stability"}
→ RSM: belief_count=1, value_count=1, determinism_emphasis=0.5, stability_emphasis=0.5
```

## Next Steps

1. Update `pmm/tests/test_mirror_rsm.py` to test claim extraction instead of keyword counting
2. Add integration test with real Echo session data
3. Document claim format in white-paper
4. Add `/claims` CLI command to view active claims

---

**This is the change the white-paper was already assuming existed.**
