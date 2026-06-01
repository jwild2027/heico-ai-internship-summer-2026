# Streamlit trace target repo-wide fix

Fixes trace target inference when an ATA code such as `25-21-00` is also mistakenly detected by loose part-number logic.

The patch script searches the repo for `infer_trace_target` and replaces its body so target priority is:

1. page ID
2. ATA code
3. part number

Run:

```bash
python scripts/apply_streamlit_trace_target_repo_fix.py
python -m pytest tests/unit/test_tiff_streamlit_trace_feedback.py tests/unit/test_tiff_streamlit_api_client.py -q
```
