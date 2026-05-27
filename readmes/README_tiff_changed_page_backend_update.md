# Changed-page backend update

This patch adds the first true changed-page backend update path.

The existing full backend rebuild remains the default.  The new path can be used
when `changed_tiffs.txt` contains only a small number of changed pages.

## New command

```bash
python scripts/update_changed_page_backend.py \
  --config local_config.yaml \
  --changed-list local_data/changed_tiffs.txt
```

It refreshes only pages that match changed TIFF paths:

1. `pages`, `page_fts`, and `part_mentions`
2. `ocr_clean_pages`
3. `part_catalog` rows for affected pages
4. `part_catalog_mentions_clean` rows for affected pages
5. `part_catalog_clean` rows for affected part numbers
6. `rag_chunks` for affected pages
7. embeddings for changed chunks only, via `build_rag_embeddings.py`
8. QA and eval reports

## Incremental pipeline integration

The regular safe option remains:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml
```

To try changed-page backend mode:

```bash
python scripts/run_incremental_tiff_pipeline.py \
  --config local_config.yaml \
  --backend-mode changed-pages
```

You can also add this to `local_config.yaml`:

```yaml
backend_mode: changed-pages
```

## Why this matters

For 509 pages, a full backend rebuild is fine.  For a 5 TB collection, one
changed TIFF should not force all search/RAG rows to be rebuilt.  This patch is
the bridge to page-scoped backend updates.
