# TRACE-Net Graph Writeback Dry Run / Graph UI Overlay v1

Step 19 consumes the Step 18 element-to-graph attachment plan and produces a graph-UI-ready overlay. It is deliberately read-only.

## Purpose

The overlay makes the enriched TRACE-Net graph inspectable before writing anything to Postgres. It represents pages, table elements, rows, cells, visual regions, callout candidates, fishnet retry plans, evidence candidates, citations, and trust authority nodes.

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No source-truth mutation.
- No direct answer permission.
- No claim-proof permission.
- Retrieval-only nodes remain retrieval-only.
- Existing nomenclature and ContextV2 graph visibility must be preserved.

## Build

```bash
python scripts/build_trace_net_graph_writeback_overlay_v1.py \
  --attachment-plan local_data/organization/trace_net/element_graph_attachment/trace_net_element_graph_attachment_plan_v1.json \
  --graph-explorer-dir local_data/organization/trace_net/graph_explorer \
  --output-dir local_data/organization/trace_net/graph_writeback_overlay \
  --mode dry-run \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-page-nodes 509 \
  --min-table-cell-nodes 3090 \
  --min-visual-nodes 1018 \
  --min-fishnet-nodes 509 \
  --min-citation-edges 1 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-attachment-quality-pass \
  --require-graph-explorer-quality-pass \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_graph_writeback_overlay_v1_quality.py \
  --report-path local_data/organization/trace_net/graph_writeback_overlay/trace_net_graph_writeback_overlay_v1.json \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-page-nodes 509 \
  --min-table-cell-nodes 3090 \
  --min-visual-nodes 1018 \
  --min-fishnet-nodes 509 \
  --min-citation-edges 1 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-attachment-quality-pass \
  --require-graph-explorer-quality-pass \
  --write-json
```

## Outputs

Generated files are written under:

```text
local_data/organization/trace_net/graph_writeback_overlay/
```

Expected files:

```text
trace_net_graph_writeback_overlay_v1.json
trace_net_graph_writeback_overlay_v1_nodes.jsonl
trace_net_graph_writeback_overlay_v1_edges.jsonl
trace_net_graph_writeback_overlay_v1_summary.json
trace_net_graph_writeback_overlay_v1_manifest.json
trace_net_graph_writeback_overlay_v1_quality.json
trace_net_graph_writeback_overlay_v1.md
trace_net_graph_writeback_overlay_v1.html
```

## Next step

After this dry-run overlay passes, the next stage is Graph UI Overlay / optional Postgres Writeback v1. Start with UI overlay or dry-run only; do not mutate Postgres until the overlay quality gate passes cleanly.
