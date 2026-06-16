# TRACE-Net Hybrid Retrieval v2 script import fix

This patch fixes direct script execution from Git Bash/Windows.

The unit tests passed because pytest adds the repository root to `sys.path`, but direct calls like:

```bash
python scripts/build_trace_net_hybrid_retrieval_v2.py ...
```

can fail with:

```text
ModuleNotFoundError: No module named 'tiff'
```

The fix inserts the repository root into `sys.path` at the top of the build and quality scripts before importing `tiff.trace_net_hybrid_retrieval_v2`.

Files changed:

```text
scripts/build_trace_net_hybrid_retrieval_v2.py
scripts/check_trace_net_hybrid_retrieval_v2_quality.py
```
