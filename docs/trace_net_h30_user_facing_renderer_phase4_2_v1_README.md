# TRACE-Net H30 Phase 4.2 — User-Facing Renderer Hardening v1

This phase hardens only query-claim scoping and user-facing presentation.

## Changes

- Adds a global sanitizer for internal retrieval IDs, long hashes, and tunnel labels.
- Adds readable Markdown renderers for navigation, OCR, authority, multi-claim, and aggregation routes.
- Collapses duplicate page/claim rows and emits one evidence-status footer.
- Shows explicit `Not stored` values for missing OCR engine and confidence metadata.
- Treats `safe to install`, installation eligibility, and installation authority as authority scope rather than a procedure request unless installation steps or instructions are explicitly requested.
- Treats exact part numbers as authority search scope rather than a second claim unless identity is explicitly requested.

## Safety contract

- Read-only presentation overlay.
- No PostgreSQL, Qdrant, or OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No promotion of visual, OCR, table, graph, semantic, candidate, summary, or Engram guidance into proof.
- Existing deterministic evidence and authority gates remain in force.

## Files

- `scripts/trace_net_h30_user_facing_renderer_v1.py`
- `scripts/serve_trace_net_cognitive_router_v1.py`
- `tests/unit/test_trace_net_h30_user_facing_renderer_v1.py`
- `docs/trace_net_h30_user_facing_renderer_phase4_2_v1_README.md`

## Focused tests

```bash
python -m pytest -q \
  tests/unit/test_trace_net_cognitive_router_v1.py \
  tests/unit/test_trace_net_h30_user_facing_renderer_v1.py \
  tests/unit/test_trace_net_full_gemma_cognitive_v1.py
```

Expected on the Phase 4.1 base: `28 passed` (`13 + 8 + 7`). If the existing Gemma test count differs, require all selected tests to pass rather than relying only on the total.

## Live output gates

1. No `::` retrieval identifiers or long internal hashes are user-visible.
2. OCR output always shows page, evidence status, engine, confidence, and readable text columns.
3. `safe to install` routes to authority verification without an unrelated Procedure claim.
4. Explicit installation-step requests still preserve a procedure claim.
5. Multi-claim output uses one row per claim and one evidence-status footer.
6. No authority claim is confirmed without explicit authority evidence.
