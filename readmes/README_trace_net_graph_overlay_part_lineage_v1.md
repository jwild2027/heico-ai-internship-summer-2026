# TRACE-Net Graph Overlay PartCandidate Page-Lineage v1

Step 19.1 refines the Step 19 dry-run graph overlay before Leiden/community detection.

The Step 19 overlay is safe, but `PartCandidate` nodes are cross-page bridge nodes. They may not have one single `page_id`, which is correct for an entity-like node, but Leiden and graph review need explicit source-page lineage. This module propagates lineage from `MAY_REFER_TO_PART` edges and neighboring page-scoped nodes into each `PartCandidate` node.

## Safety contract

This step is read-only:

- no Postgres mutation
- no Qdrant mutation
- no source-truth mutation
- no direct-answer permission
- no claim-proof permission

`PartCandidate` nodes remain advisory/cross-page graph bridge nodes. They do not prove part claims by themselves.

## Inputs

```text
local_data/organization/trace_net/graph_writeback_overlay/trace_net_graph_writeback_overlay_v1.json
```

## Outputs

```text
local_data/organization/trace_net/graph_overlay_part_lineage/
  trace_net_graph_overlay_part_lineage_v1.json
  trace_net_graph_overlay_part_lineage_v1_nodes.jsonl
  trace_net_graph_overlay_part_lineage_v1_edges.jsonl
  trace_net_graph_overlay_part_lineage_v1_part_candidates.jsonl
  trace_net_graph_overlay_part_lineage_v1_summary.json
  trace_net_graph_overlay_part_lineage_v1_manifest.json
  trace_net_graph_overlay_part_lineage_v1_quality.json
  trace_net_graph_overlay_part_lineage_v1.md
  trace_net_graph_overlay_part_lineage_v1.html
```

## Build

```bash
python scripts/build_trace_net_graph_overlay_part_lineage_v1.py \
  --graph-overlay-report local_data/organization/trace_net/graph_writeback_overlay/trace_net_graph_writeback_overlay_v1.json \
  --output-dir local_data/organization/trace_net/graph_overlay_part_lineage \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-part-candidate-nodes 301 \
  --min-part-candidate-nodes-with-source-page-ids 301 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-overlay-quality-pass \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_graph_overlay_part_lineage_v1_quality.py \
  --report-path local_data/organization/trace_net/graph_overlay_part_lineage/trace_net_graph_overlay_part_lineage_v1.json \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-part-candidate-nodes 301 \
  --min-part-candidate-nodes-with-source-page-ids 301 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-overlay-quality-pass \
  --write-json
```

## Expected results

```text
part_candidate_node_count: 301
part_candidate_nodes_with_source_page_ids_count: 301
part_candidate_missing_source_page_ids_count: 0
page_scoped_missing_page_id_count: 0
orphan_edge_count: 0
source_truth_mutation_allowed_count: 0
```

After this passes, Step 20 Leiden can use `PartCandidate` nodes as clean cross-page bridge entities.
