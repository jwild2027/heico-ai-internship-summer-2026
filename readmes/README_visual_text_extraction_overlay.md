# HEICO visual text extraction overlay

This patch adds the next OCR layer: **model-assisted visual text extraction**.

Traditional OCR reads plain text. This overlay asks a vision-capable model to turn visual page content into searchable text:

- tables and grids
- figures and diagrams
- charts and graphs
- labels, arrows, callouts, legends, dimensions, and notes
- part numbers, item numbers, quantities, nomenclature, figure references, and sheet references visible in the scan

It is additive. It does **not** rewrite the core graph. It writes a separate overlay under:

```text
local_data/organization/visual_text/
```

## New files

```text
tiff/visual_text_extraction.py
tiff/visual_text_extraction_quality.py
scripts/run_visual_text_extraction.py
scripts/check_visual_text_extraction_quality.py
tests/unit/test_tiff_visual_text_extraction.py
tests/unit/test_tiff_visual_text_extraction_quality.py
README_visual_text_extraction_overlay.md
```

## Output files

```text
local_data/organization/visual_text/visual_text_extraction.jsonl
local_data/organization/visual_text/visual_text_extraction_summary.json
local_data/organization/visual_text/visual_text_corpus.md
local_data/organization/visual_text/visual_text_graph_nodes.json
local_data/organization/visual_text/visual_text_graph_edges.json
local_data/organization/visual_text/visual_text_quality.json
```

The graph overlay shape is:

```text
Page -> HAS_VISUAL_TEXT -> VisualTextContext -> DERIVED_FROM -> visual_text_extraction evidence source
VisualTextContext -> SUMMARIZES_VISUAL_CONTENT_OF -> Page
```

## Test

```bash
python -m pytest \
  tests/unit/test_tiff_visual_text_extraction.py \
  tests/unit/test_tiff_visual_text_extraction_quality.py \
  -q
```

Expected:

```text
....... [100%]
7 passed
```

## Safe pilot without a model

Use the `planned` provider first. It selects pages, writes records, corpus, and graph overlay, but does not call a model.

```bash
python scripts/run_visual_text_extraction.py \
  --provider planned \
  --max-pages 10 \
  --overwrite
```

Then run the quality gate:

```bash
python scripts/check_visual_text_extraction_quality.py --write-json
```

## Mock model smoke test

This exercises the model-call path without requiring a real model:

```bash
python scripts/run_visual_text_extraction.py \
  --provider mock \
  --max-pages 10 \
  --overwrite
```

## Real local vision-model pilot

Use any local Ollama model that supports image input. Replace the model name with the one installed on your machine.

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:latest \
  --max-pages 5 \
  --overwrite
```

If the 5-page output looks good, scale slowly:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:latest \
  --max-pages 50 \
  --overwrite
```

Then run all selected visual pages:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:latest \
  --all-pages \
  --overwrite
```

## Selecting what to process

By default, the script selects pages with these roles/classes:

```text
page roles: figure, table, procedure, parts_list
image classes: likely_figure_or_diagram, likely_table_or_grid, likely_text_or_parts_list
```

You can change the selection:

```bash
python scripts/run_visual_text_extraction.py \
  --provider planned \
  --page-roles table,figure \
  --image-classes likely_table_or_grid,likely_figure_or_diagram \
  --max-pages 20 \
  --overwrite
```

Process one page:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:latest \
  --page-id t_p_120_1176_p000083 \
  --overwrite
```

Include blank pages:

```bash
python scripts/run_visual_text_extraction.py \
  --provider planned \
  --include-blank \
  --max-pages 20 \
  --overwrite
```

## Quality gate

Allow planned records during development:

```bash
python scripts/check_visual_text_extraction_quality.py --write-json
```

Require real model output:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --disallow-planned \
  --write-json
```

## Why this is separate from OCR

OCR extracts text glyphs. This overlay produces **visual text context** from the image itself. That means graphs, tables, diagrams, callout relationships, arrows, labels, and chart structure become searchable text and can later feed RAG/vector indexing.
