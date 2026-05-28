# TIFF Streamlit UI polish

This patch makes the local Streamlit UI easier to read without changing backend behavior.

It updates:

```text
apps/streamlit/tiff_rag_ui.py
tiff/streamlit_ui_backend.py
tests/unit/test_tiff_streamlit_ui_polish.py
```

Changes:

```text
Browse tab:
  uses tables/dataframes instead of code blocks
  shows raw JSON only inside expanders

Ask tab:
  separates answer, source list, and raw CLI output
  shows LLM/embedding flags as small metrics

Sources tab:
  shows page/source rows as a table
```

Run:

```bash
python -m pytest tests/unit/test_tiff_streamlit_ui_backend.py tests/unit/test_tiff_streamlit_ui_polish.py -q
python scripts/check_tiff_ui_ready.py --strict
python -m streamlit run apps/streamlit/tiff_rag_ui.py
```
