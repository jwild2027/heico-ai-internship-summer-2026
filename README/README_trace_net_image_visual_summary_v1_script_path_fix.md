# TRACE-Net Image Visual Summary v1 Script Path Fix

This focused fix updates the Image Visual Summary v1 script entrypoints so they can be run directly with:

```bash
python scripts/build_trace_net_image_visual_summary_v1.py ...
python scripts/check_trace_net_image_visual_summary_v1_quality.py ...
```

The original tests passed because pytest places the repository root on `sys.path`, but direct script execution starts with `scripts/` on `sys.path`, so `from tiff...` could fail with `ModuleNotFoundError: No module named 'tiff'`.

The scripts now bootstrap the repository root before importing `tiff.trace_net_image_visual_summary_v1`.

Safety contract is unchanged: no Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.
