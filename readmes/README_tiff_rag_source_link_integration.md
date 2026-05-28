# TIFF RAG Source-Link Integration

This patch wires the `source_links` table into RAG retrieval, answer context, manifests, and quality gates.

## What changed

- Retrieved `RagSource` rows are enriched from `source_links` when the table exists.
- RAG source dictionaries now include `rescarta_url`, `source_url`, `tiff_uri`, and `ocr_uri`.
- Answer context and deterministic answers display ResCarta/source URLs before raw TIFF/OCR paths.
- Pipeline manifests count `source_links` and list source-link report artifacts.
- Quality gates can require that `source_links` is populated.

## Install/test

```bash
python -m pytest tests/unit/test_tiff_rag_source_link_integration.py tests/unit/test_tiff_source_links.py tests/unit/test_tiff_pipeline_manifest.py tests/unit/test_tiff_pipeline_quality.py -q
```

## Typical workflow

```bash
python scripts/build_rescarta_mapping.py --config local_config.yaml --rescarta-url-template "http://localhost:8080/rescarta/{object_id}/{page_id}" --write-report
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/show_pipeline_status.py
python scripts/check_pipeline_quality.py
python scripts/ask_tiff_rag.py --config local_config.yaml "What is part number 120-37313-001?"
```

The answer sources should now include ResCarta/source URLs when `source_links` has been built.
