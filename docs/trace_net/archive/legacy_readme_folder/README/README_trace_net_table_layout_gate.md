# TRACE-Net table layout gate

This patch makes the table crop/tile executor less sensitive by adding a final lightweight image-layout gate after the graph gate.

The previous graph gate used page role, image classification, and TRACE-Net review traits. That correctly blocked engineering drawings/figure pages, but prose/reference pages could still slip through when they were labeled `table` or `likely_table_or_grid`.

The new layout gate reads the page TIFF before tiling and computes cheap projection features:

- repeated row bands
- active column groups
- horizontal/vertical table-rule signals
- ink density
- prose-like layout penalty

It keeps dense table/list pages such as effective-page tables and blocks prose/reference pages that look grid-like in metadata but do not have table-like layout structure.

## New defaults

The gate is enabled by default:

```bash
python scripts/run_trace_net_table_tiles.py \
  --routes high \
  --include-medium \
  --tiles-per-page 6 \
  --max-image-edge 1800 \
  --open
```

New options:

```bash
--no-table-layout-gate
--min-table-layout-score 3
--table-layout-probe-edge 1200
```

Use `--no-table-layout-gate` only when comparing to the previous behavior.

## Expected effect on the current 25-page pilot

The gate should continue allowing true effective-page table pages such as p000009-p000011, while blocking prose/reference pages such as p000020, p000021, and p000023. Engineering drawings/figure pages should remain blocked by the graph gate.

## Quality

Run:

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_table_tiles.py \
  tests/unit/test_tiff_trace_net_table_tile_quality.py \
  -q
```

Then rerun the table tile executor and quality gate:

```bash
python scripts/run_trace_net_table_tiles.py \
  --routes high \
  --include-medium \
  --tiles-per-page 6 \
  --max-image-edge 1800 \
  --open

python scripts/check_trace_net_table_tile_quality.py \
  --write-json \
  --min-records 3 \
  --min-ok-records 3 \
  --min-tile-images 18
```

The exact selected page count may be lower than before because false-positive table pages are now skipped by the layout gate.
