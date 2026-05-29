# TIFF Streamlit UI starter

This patch adds a separate local Streamlit UI for the TIFF backend:

```text
apps/streamlit/tiff_rag_ui.py
scripts/check_tiff_ui_ready.py
tiff/streamlit_ui_backend.py
tests/unit/test_tiff_streamlit_ui_backend.py
```

It does not replace the older Streamlit apps already in `apps/streamlit/`.

## What it uses

The UI reads the same artifacts that a future API/UI should consume:

```text
local_data/organization/export/manual_ata_tree.json
local_data/organization/export/ata_tree.json
local_data/organization/export/part_tree.json
local_data/organization/export/page_index.json
local_data/organization/export/organization_summary.json
local_data/pipeline_runs/latest_backend_pipeline.json
local_data/pipeline_runs/latest_quality_gate.json
```

For natural-language questions, it calls the existing command:

```bash
python scripts/ask_tiff_rag.py --config local_config.yaml "...question..."
```

## Run

From Git Bash at repo root:

```bash
python -m pytest tests/unit/test_tiff_streamlit_ui_backend.py -q
python scripts/check_tiff_ui_ready.py --strict
streamlit run apps/streamlit/tiff_rag_ui.py
```

## UI tabs

```text
Status
    pipeline/quality/export/source/OCR/incremental health

Browse
    part lookup, ATA lookup, page lookup from exported organization JSON

Ask
    user question through ask_tiff_rag.py

Sources
    page/source/TIFF/OCR lookup
```

This is intentionally local and read-only. It does not run the full pipeline, mutate data, or edit source files.
