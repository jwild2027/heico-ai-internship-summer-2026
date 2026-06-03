# TRACE-Net all-page table candidate scan

This patch adds a full-corpus table candidate scanner for TRACE-Net.

It does **not** call OCR, Ollama, or a table model. It scans all known pages using:

- `page_character_cards.json`
- `page_index.json`
- `page_image_recognition_audit.json`
- lightweight image-layout scoring over the TIFFs

It writes a TRACE-Net-compatible candidate repair plan that the existing table crop/tile executor can consume.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_table_candidate_scan.py \
  tests/unit/test_tiff_trace_net_table_candidate_quality.py \
  -q
```

## Scan all 509 pages

```bash
python scripts/plan_trace_net_table_candidates.py \
  --expect-pages 509 \
  --max-image-edge 1200 \
  --open
```

## Check candidate quality

```bash
python scripts/check_trace_net_table_candidate_quality.py \
  --write-json \
  --min-records 509 \
  --expect-pages 509 \
  --min-candidates 1 \
  --max-missing-images 0
```

## Crop/tile only pages selected by the all-page scan

The candidate scanner writes a TRACE-Net-compatible `trace_net_repair_plan.jsonl` under:

```text
local_data/organization/table_extraction/all_page_scan/trace_net_repair_plan.jsonl
```

Point the table crop/tile executor at that directory:

```bash
python scripts/run_trace_net_table_tiles.py \
  --trace-net-dir local_data/organization/table_extraction/all_page_scan \
  --routes high \
  --include-medium \
  --tiles-per-page 6 \
  --max-image-edge 1800 \
  --open
```

Then check table tiling quality. Use the actual selected count/tile count printed by the run:

```bash
python scripts/check_trace_net_table_tile_quality.py \
  --write-json \
  --min-records <SELECTED_PAGES> \
  --expect-pages <SELECTED_PAGES> \
  --min-ok-records <OK_PAGES> \
  --min-tile-images <OK_PAGES_TIMES_TILES_PER_PAGE>
```

## Concept

Current subset flow:

```text
25-page visual-text pilot -> trust traits -> repair plan -> table tiles
```

New full-corpus flow:

```text
all 509 page character cards
  -> graph/page-role gate
  -> layout image gate
  -> all-page table candidate plan
  -> table crop/tile executor
```

The next step after this is table tile OCR/extraction over pages that pass as `has_table` / table candidates.
