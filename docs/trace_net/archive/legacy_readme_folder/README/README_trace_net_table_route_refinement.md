# TRACE-Net Table Route Refinement

This patch refines the TRACE-Net repair planner so the `table_expected_but_not_extracted` trait is no longer treated as one blunt route for every page.

## What changed

The planner now separates table-missing records into route priorities:

```text
high table route
  explicit table pages / strong table-grid pages

medium table route
  parts-list, numerical-index, or index pages where table extraction may help

low candidate review
  weak table flags on front matter/text/procedure pages

not-table validation
  figure/diagram/blank/title pages where the table flag likely conflicts with page evidence
```

This keeps the future table crop/tile extractor focused on real table candidates instead of sending every visual-text record to the same expensive route.

## New route names

```text
table_crop_tile_repair_route_high
table_crop_tile_repair_route_medium
table_candidate_review_route
ocr_graph_validation_review_route
```

The old fallback route still exists for legacy records that do not contain page-role or image-class metadata:

```text
table_crop_tile_repair_route
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_repair.py \
  tests/unit/test_tiff_trace_net_repair_quality.py \
  tests/unit/test_tiff_trace_net_table_route_refinement.py \
  -q
```

## Rebuild the current repair plan

```bash
python scripts/plan_trace_net_repairs.py \
  --expect-pages 25 \
  --samples 25
```

Then run quality:

```bash
python scripts/check_trace_net_repair_quality.py \
  --write-json \
  --min-records 25 \
  --expect-pages 25 \
  --min-auto-repair-candidates 1 \
  --max-unplanned-problem-records 0
```

## Expected improvement

Before refinement, most table-missing records were grouped together:

```text
table_crop_tile_repair_route: many pages
```

After refinement, the plan should show more useful buckets, such as:

```text
table_crop_tile_repair_route_high: actual table pages
table_crop_tile_repair_route_medium: parts-list/index table candidates
table_candidate_review_route: weak candidates
ocr_graph_validation_review_route: figure/title/front-matter conflicts
```

This is the planning step before building the actual table crop/tile repair executor.
