# TRACE-Net Vector Search Smoke v1 Import Fix 2

This hotfix corrects the direct script wrappers for Step 6.

The previous import fix added the repository root to `sys.path`, but it imported
nonexistent names from `tiff.trace_net_vector_search_smoke_v1`:

- `run_main`
- `check_main`

The module exposes:

- `main`
- `quality_main`

This patch updates the wrappers to import the existing entry points while
keeping the repo-root `sys.path` fix so the scripts work from Git Bash with:

```bash
python scripts/run_trace_net_vector_search_smoke_v1.py ...
python scripts/check_trace_net_vector_search_smoke_v1_quality.py ...
```

It does not modify the vector smoke logic, Qdrant data, Ollama embeddings,
TRACE-Net payload safety, or generated `local_data` artifacts.
