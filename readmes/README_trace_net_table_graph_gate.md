# TRACE-Net table graph gate

This patch adds a stronger graph-aware eligibility gate to the TRACE-Net table crop/tile executor.

The table tiler was already driven by the TRACE-Net repair plan, but the plan can intentionally be broad. This gate checks page character-card evidence immediately before cutting tiles, using fields such as:

- page role / context role
- image-recognition class
- page/entity traits
- table-vs-figure/drawing signals

If the repair plan says a page should go to table tiling but the graph/page-card evidence says it is a figure, drawing, blank, title, or otherwise not table-like, the page is skipped instead of tiled.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_table_tiles.py \
  tests/unit/test_tiff_trace_net_table_tile_quality.py \
  -q
```

## Run high + medium with the graph gate enabled

```bash
python scripts/run_trace_net_table_tiles.py \
  --routes high \
  --include-medium \
  --tiles-per-page 6 \
  --max-image-edge 1800 \
  --open
```

The graph gate is enabled by default.

## Disable the gate for comparison

```bash
python scripts/run_trace_net_table_tiles.py \
  --routes high \
  --include-medium \
  --tiles-per-page 6 \
  --max-image-edge 1800 \
  --no-graph-table-gate \
  --open
```

## What to look for

The summary now includes fields like:

```text
skipped_graph_gate_records
graph_table_gate_blocked_records
graph_table_gate_reasons
```

A skipped page is not an error. It means TRACE-Net avoided cutting a page whose graph/page-card traits did not support table extraction.
