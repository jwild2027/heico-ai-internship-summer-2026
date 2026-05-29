# TIFF Streamlit API mode

This patch adds a separate Streamlit app that talks to the FastAPI boundary instead of directly reading local files/scripts.

## Run the API

```bash
python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

## Run the API-mode UI

```bash
python -m streamlit run apps/streamlit/tiff_api_ui.py
```

Optional API URL override:

```bash
python -m streamlit run apps/streamlit/tiff_api_ui.py -- --api-url http://127.0.0.1:8000
```

or:

```bash
TIFF_API_URL=http://127.0.0.1:8000 python -m streamlit run apps/streamlit/tiff_api_ui.py
```

## Test

```bash
python -m pytest tests/unit/test_tiff_streamlit_api_client.py -q
```

## Tabs

- Ask: calls `POST /ask`
- Lookup: calls organization endpoints for parts/pages/ATA/summary
- Trace: calls part/page/vector trace endpoints
- Feedback: calls `POST /feedback` and `GET /feedback/summary`
- Status / Quality: calls `GET /status`

This app is intentionally separate from the existing local-file Streamlit UI so the current prototype remains available.
