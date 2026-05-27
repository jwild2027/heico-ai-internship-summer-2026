# TIFF Backend Pipeline Wrapper

This patch adds a single wrapper command for the current local TIFF search/RAG backend.
It does not replace the earlier inventory/OCR crawler yet. It orchestrates the backend rebuild from the current ResCarta staging export.

## New command

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml --reset-embeddings
```

The wrapper runs, in order:

1. `scripts/build_tiff_search_index.py`
2. `scripts/rebuild_clean_part_catalog.py`
3. `scripts/build_rag_chunks.py`
4. `scripts/build_rag_embeddings.py`
5. `scripts/report_part_catalog_qa.py`
6. `scripts/evaluate_rag_questions.py`

If the eval question file does not exist, the wrapper creates the starter set first.

## Dry run

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml --dry-run
```

## Resume from RAG chunks only

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml --skip-search-index --skip-part-catalog
```

## Skip QA/eval

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml --skip-qa --skip-eval
```

## Why this exists

Before this wrapper, the backend rebuild required several long commands:

```text
build search index
rebuild clean part catalog
build RAG chunks
build embeddings
run QA
run evaluation
```

This wrapper makes the current MVP repeatable and prepares the project for the later fully incremental pipeline.
