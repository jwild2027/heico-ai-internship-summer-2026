# TIFF document graph quality gate

Adds graph/context/source traceability checks to the local TIFF backend quality gate.

## New checks

- graph artifacts exist
- every page has a source link
- every page has AI context
- page context generation errors are zero, while empty-OCR contexts are tracked separately
- sample part trace works: part -> pages -> source links -> AI context
- sample page trace works: page -> document/ATA/source/context
- simulated Qdrant payload trace works: page_id/chunk_id -> graph/source/context
- optional user-query regression results are present and all passing

## Commands

```bash
python -m pytest tests/unit/test_tiff_document_graph_quality.py -q
python scripts/check_document_graph_quality.py --write-json
python scripts/refresh_graph_quality_summary.py
python scripts/check_pipeline_quality.py --require-incremental-smoke --require-user-query-tests
```

Use `--no-require-graph-quality` only if you need the old behavior before graph artifacts have been generated.
