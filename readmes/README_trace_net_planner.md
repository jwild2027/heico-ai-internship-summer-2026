# TRACE-Net planner

TRACE-Net means **Traceable Routed Adaptive Context Extraction Network**.

This patch adds the first concrete TRACE-Net layer: a planner that reads the current page graph/card/visual-text artifacts and chooses the next extraction route for each page.

It does not call Ollama, OCR, or a table model. It creates a plan.

## Why this exists

The visual-text pilot showed that one full-page vision prompt cannot reliably do every job:

- figures need label/callout extraction
- dense tables need crop/tile/table extraction
- parts-list pages need OCR and part-catalog validation
- front matter needs title/header extraction
- blank pages should be skipped
- risky visual model output needs review before RAG use

TRACE-Net routes pages before extraction.

## New files

```text
tiff/trace_net.py
scripts/plan_trace_net_routes.py
scripts/check_trace_net_plan_quality.py
tests/unit/test_tiff_trace_net.py
tests/unit/test_tiff_trace_net_quality.py
README_trace_net_planner.md
```

## Run tests

```bash
python -m pytest tests/unit/test_tiff_trace_net.py tests/unit/test_tiff_trace_net_quality.py -q
```

## Build a TRACE-Net plan

```bash
python scripts/plan_trace_net_routes.py --expect-pages 509 --samples 20
```

Outputs:

```text
local_data/organization/trace_net/trace_net_plan.json
local_data/organization/trace_net/trace_net_plan.jsonl
local_data/organization/trace_net/trace_net_plan_summary.json
local_data/organization/trace_net/trace_net_graph_nodes.json
local_data/organization/trace_net/trace_net_graph_edges.json
local_data/organization/trace_net/trace_net_plan_review.md
```

## Quality gate

```bash
python scripts/check_trace_net_plan_quality.py --write-json --expect-pages 509 --min-records 509
```

## Route types

```text
blank              -> skip_blank
front_matter       -> title_header_context_route
figure_diagram     -> vision_figure_callout_route
table_grid         -> grit_table_crop_tile_route
parts_list         -> ocr_part_catalog_validation_route
procedure_text     -> ocr_context_warning_note_route
general_text       -> ocr_context_general_route
```

## How this connects to the future algorithm

TRACE-Net is the orchestration layer:

```text
Page character card
  -> route decision
  -> extractor recommendation
  -> fishnet safety settings
  -> review/trust scoring
  -> graph overlay
```

The next major extractor should be `grit_table_crop_tile_route`, a table-specific route for dense parts-list/effective-page tables.
