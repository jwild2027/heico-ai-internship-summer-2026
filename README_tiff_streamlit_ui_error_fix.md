# TIFF Streamlit UI error/warning fix

Fixes two UI patch issues:

- Restores compatibility helper functions expected by `tests/unit/test_tiff_streamlit_ui_backend.py`:
  - `ata_header`
  - `page_header`
  - `part_header`
  - `source_table_rows`
  - `page_table_rows`
  - `parse_rag_stdout`
- Replaces deprecated Streamlit `use_container_width=True` calls with `width="stretch"`.

Run:

```bash
python -m pytest tests/unit/test_tiff_streamlit_ui_backend.py tests/unit/test_tiff_streamlit_ui_polish.py -q
python scripts/check_tiff_ui_ready.py --strict
python -m streamlit run apps/streamlit/tiff_rag_ui.py
```
