# TIFF Page Context Progress Patch

Adds per-page progress logging for the AI page-context scan and fixes page-context graph linkage counts in the inspector.

## What changed

- `scripts/generate_page_contexts.py`
  - Adds `--progress` to print one line after each scanned/generated/skipped page.
  - Progress includes page ID, role, confidence, quality score, elapsed seconds, and approximate token count.
  - Summary includes total elapsed, average/page elapsed, and approximate total tokens.

- `tiff/page_context.py`
  - Adds timing and approximate token metadata to each `PageContext` record.
  - Stores a simple `quality_score` derived from confidence and whether the context had a warning/error.

- `tiff/page_context_inspector.py`
  - Reads graph linkage counts from the current nested `graph_summary.json` shape.
  - Fixes `page_context nodes: None` / `HAS_CONTEXT edges: None` display.

## Suggested command

```bash
python scripts/generate_page_contexts.py --model gemma3:12B --limit 100 --write-json --show-error-details --progress
python scripts/export_document_organization_graph.py --strict
python scripts/inspect_page_contexts.py --strict --write-json
```

For normal incremental generation, omit `--force` so existing contexts are skipped instead of regenerated.
