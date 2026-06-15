# TRACE-Net table crop/tile executor v1

This patch starts **Part C: table extraction** with a safe first step.

It does **not** call OCR, Ollama, or any table model yet. It reads the TRACE-Net repair plan, selects table-route pages, loads their TIFF/page images, crops page margins, creates horizontal tile images, and writes review/graph/quality artifacts.

## Files added

```text
tiff/trace_net_table_tiles.py
scripts/run_trace_net_table_tiles.py
scripts/check_trace_net_table_tile_quality.py
tests/unit/test_tiff_trace_net_table_tiles.py
tests/unit/test_tiff_trace_net_table_tile_quality.py
README_trace_net_table_tiles.md
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_table_tiles.py \
  tests/unit/test_tiff_trace_net_table_tile_quality.py \
  -q
```

## Run high-priority table route only

This is the safest first run. It should target the high-priority table pages from the refined TRACE-Net repair plan.

```bash
python scripts/run_trace_net_table_tiles.py \
  --routes high \
  --tiles-per-page 6 \
  --max-image-edge 1800 \
  --open
```

## Run high + medium table routes

```bash
python scripts/run_trace_net_table_tiles.py \
  --routes high \
  --include-medium \
  --tiles-per-page 6 \
  --max-image-edge 1800 \
  --open
```

## Quality gate

For high-only, expect at least 4 tiled pages in the current 25-page pilot:

```bash
python scripts/check_trace_net_table_tile_quality.py \
  --write-json \
  --min-records 4 \
  --expect-pages 4 \
  --min-ok-records 4 \
  --min-tile-images 24
```

For high + medium, expect at least 17 tiled pages:

```bash
python scripts/check_trace_net_table_tile_quality.py \
  --write-json \
  --min-records 17 \
  --expect-pages 17 \
  --min-ok-records 17 \
  --min-tile-images 102
```

## Outputs

```text
local_data/organization/table_extraction/table_tile_plan.json
local_data/organization/table_extraction/table_tile_plan.jsonl
local_data/organization/table_extraction/table_tile_summary.json
local_data/organization/table_extraction/table_tile_graph_nodes.json
local_data/organization/table_extraction/table_tile_graph_edges.json
local_data/organization/table_extraction/table_tile_review.md
local_data/organization/table_extraction/table_tile_review.html
local_data/organization/table_extraction/tiles/<page_id>/full_preprocessed.png
local_data/organization/table_extraction/tiles/<page_id>/tile_001.png
...
```

## Purpose

This proves the image routing and tiling layer before adding OCR/model extraction over each tile.

Current TRACE-Net flow:

```text
trust traits
  -> repair planner
  -> refined table route
  -> table crop/tile executor v1
  -> future tile OCR/model extraction
```
