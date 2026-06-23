# TRACE-Net E2E Codebase Checklist v1

This local read-only checklist prints a terminal view of the current TRACE-Net E2E RAG state.

It checks:

- key E2E source modules are present
- table exact/search/bridge artifacts exist and are PASS
- query planning/routing, planned hybrid retrieval, context pack, sufficiency, final gate, RAG demo, API wrapper, and local endpoint artifacts exist and are PASS
- authority/write counters remain zero when present
- the current WebUI demo path is artifact-backed planned hybrid retrieval, not yet a fully dynamic per-query live runtime

Run:

```bash
python scripts/run_trace_net_e2e_codebase_checklist_v1.py \
  --output-dir local_data/organization/trace_net/e2e_codebase_checklist
```

Use `--fail-on-blocking` in CI or before commits if you want MISSING/FAIL items to return a nonzero exit code.
