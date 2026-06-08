# TRACE-Net Table Tile Text Classifier/Refiner v1

This patch adds a deterministic refinement layer after `TRACE-Net table tile text extraction`.

It reads:

```text
local_data/organization/table_extraction/table_tile_text/table_tile_text_records.jsonl
local_data/organization/export/part_tree.json
```

and writes:

```text
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_records.jsonl
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_summary.json
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_corpus.md
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_review.html
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_graph_nodes.json
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_graph_edges.json
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_quality.json
```

## What it does

It separates tile-text tokens into safer classes:

```text
catalog_supported_part_number
unsupported_part_candidate
ata_code
index_label
page_reference
date
noise
```

Examples:

```text
120-50645-009      -> catalog_supported_part_number, if found in part_tree
120-99999-001      -> unsupported_part_candidate
25-21-00           -> ata_code
25-Numerical       -> index_label
25-Vendors         -> index_label
20-IFL             -> index_label / section label
```

This prevents labels such as `25-Numerical` from being treated as canonical part numbers.

## Commands

```bash
python scripts/refine_trace_net_table_tile_text.py --open
```

Quality:

```bash
python scripts/check_trace_net_table_tile_text_refined_quality.py \
  --write-json \
  --min-records 120 \
  --min-catalog-supported-records 1 \
  --max-error-records 0 \
  --max-index-labels-in-canonical-parts 0
```

For a small pilot:

```bash
python scripts/refine_trace_net_table_tile_text.py --max-records 20 --open
python scripts/check_trace_net_table_tile_text_refined_quality.py \
  --write-json \
  --min-records 20 \
  --max-error-records 0 \
  --max-index-labels-in-canonical-parts 0
```

## Why this exists

The first table tile text extractor is intentionally broad. It can recover useful part-number evidence, but it can also catch table/index labels like:

```text
25-Numerical
25-Vendors
25-21-00
```

This refiner makes the table evidence safer before it is fed back into Evidence Consensus and trust traits.
