# Streamlit trace and feedback UI polish

This patch improves the API-mode Streamlit app.

## Adds

- A cleaner `Ask` tab with answer controls.
- `Trace this answer` support that detects a page, part, or ATA target.
- A clearer `Trace / why this answer?` tab for part/page/vector traceability.
- Source cards showing page/source/TIFF/OCR information when available.
- AI page-context snippets from graph trace payloads.
- A feedback form with categories and review hints.
- Feedback summary stats and recent feedback display.
- Pure helper tests that do not require Streamlit.

## Run

Start FastAPI:

```bash
python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000
```

Run UI:

```bash
python -m streamlit run apps/streamlit/tiff_api_ui.py
```

## Test

```bash
python -m pytest tests/unit/test_tiff_streamlit_trace_feedback.py tests/unit/test_tiff_streamlit_api_client.py -q
```
