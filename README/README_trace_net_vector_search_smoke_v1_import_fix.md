# TRACE-Net Vector Search Smoke v1 Import Fix

This patch fixes direct execution of the Step 6 smoke-test wrappers from Git Bash/PowerShell:

```bash
python scripts/run_trace_net_vector_search_smoke_v1.py ...
python scripts/check_trace_net_vector_search_smoke_v1_quality.py ...
```

Python sets `sys.path[0]` to `scripts/` when a script is executed by path. The wrappers now insert the repository root into `sys.path` before importing from `tiff/`.

No TRACE-Net retrieval, Qdrant, payload, or safety logic is changed.
