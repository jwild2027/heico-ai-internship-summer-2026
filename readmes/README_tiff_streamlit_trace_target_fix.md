# Streamlit trace-target detection fix

This patch fixes trace target inference so ATA codes such as `25-21-00` are not mistaken for part numbers.

Detection order is now:

1. page id
2. ATA code
3. part number

Run:

```bash
python scripts/apply_streamlit_trace_target_fix.py
python -m pytest tests/unit/test_tiff_streamlit_trace_feedback.py tests/unit/test_tiff_streamlit_api_client.py -q
```
