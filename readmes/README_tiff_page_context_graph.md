# TIFF page context graph layer

This patch adds optional AI-generated page context nodes to the document organization graph.

It adds:

```text
tiff/page_context.py
scripts/generate_page_contexts.py
tiff/document_organization_graph.py
scripts/export_document_organization_graph.py
tests/unit/test_tiff_page_context_graph.py
```

## What it does

The generator reads the organization export page index, reads each page OCR text, and asks an Ollama model to produce a small structured context record:

```text
Page
  HAS_CONTEXT
    PageContext
```

A PageContext record includes:

```text
short_summary
page_role
topics
important_parts
confidence
model
prompt_version
source OCR/page metadata
```

The graph export then adds:

```text
page_context nodes
HAS_CONTEXT edges
SUMMARIZES edges
HIGHLIGHTS_PART edges
TAGGED_AS topic edges
GENERATED_FROM OCR edges when possible
```

This is derived/helper data. The source of truth remains the TIFF/OCR/ResCarta source page.

## Smoke test without the model

```bash
python scripts/generate_page_contexts.py --dry-run --limit 10 --force --write-json
python scripts/export_document_organization_graph.py --strict
```

## Gemma AI scan

Start small:

```bash
python scripts/generate_page_contexts.py --model gemma3:12B --limit 10 --force --write-json
python scripts/export_document_organization_graph.py --strict
```

Full current sample scan:

```bash
python scripts/generate_page_contexts.py --model gemma3:12B --force --write-json
python scripts/export_document_organization_graph.py --strict
```

The full sample has 509 pages, so the full Gemma scan can take a while. Use `--limit` first.

## Output files

```text
local_data/organization/context/page_contexts.json
local_data/organization/graph/graph_nodes.json
local_data/organization/graph/graph_edges.json
local_data/organization/graph/graph_summary.json
```
