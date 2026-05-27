# TIFF source-link pipeline/quality integration

This patch moves the source-link audit into the normal backend pipeline and quality gate.

## What it adds

The normal backend pipeline now includes:

```text
search_index
part_catalog
rag_chunks
rag_embeddings
part_catalog_qa
part_catalog_qa_triage
source_link_audit
rag_eval
```

The `source_link_audit` step writes:

```text
local_data/source_links/source_link_audit.json
```

The pipeline manifest now includes a `source_link_summary`, and `show_pipeline_status.py` prints it.

The quality gate now fails if local source review is broken, for example:

```text
pages without source links > 0
missing TIFF files > 0
missing OCR files > 0
missing source URLs > 0
sample source queries miss
```

The quality gate does **not** fail on placeholder/local ResCarta URLs by default. That is intentional until the real company ResCarta deep-link format is known.

## Useful commands

```bash
python -m pytest tests/unit/test_tiff_source_link_pipeline_quality.py -q
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/check_pipeline_quality.py
python scripts/show_pipeline_status.py
```

Later, after the real ResCarta URL format is known, use:

```bash
python scripts/check_pipeline_quality.py --require-real-rescarta
```
