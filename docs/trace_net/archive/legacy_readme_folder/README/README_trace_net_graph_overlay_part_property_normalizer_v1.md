# TRACE-Net Graph Overlay PartCandidate Property Normalizer v1

Step 19.2 normalizes `PartCandidate` node properties in the graph overlay after Step 19.1 has added source-page lineage.

## Purpose

Step 19.1 made every `PartCandidate` a cross-page entity with `source_page_ids`. Some nodes still had a readable part number only in the node ID or label, while `properties.part_number` was missing.

This step copies or derives:

- `part_number`
- `canonical_part_candidate`
- `part_family`
- `part_number_source`

from existing node fields such as:

- `properties.part_number`
- `properties.canonical_part_candidate`
- node label
- `part_candidate::<part-number>` node ID

## Safety

This is a read-only graph overlay transform.

It does not:

- write to Postgres
- write to Qdrant
- mutate source truth
- grant answer authority
- allow retrieval-only nodes to answer

`PartCandidate` remains a cross-page graph/retrieval bridge node, not answer proof.

## Build

```bash
python scripts/build_trace_net_graph_overlay_part_property_normalizer_v1.py \
  --graph-overlay-part-lineage local_data/organization/trace_net/graph_overlay_part_lineage/trace_net_graph_overlay_part_lineage_v1.json \
  --output-dir local_data/organization/trace_net/graph_overlay_part_property_normalizer \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-part-candidate-nodes 301 \
  --min-part-candidate-nodes-with-source-page-ids 301 \
  --min-part-candidate-nodes-with-part-number 301 \
  --min-part-families 1 \
  --min-table-cell-nodes 3090 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-lineage-quality-pass \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_graph_overlay_part_property_normalizer_v1_quality.py \
  --report-path local_data/organization/trace_net/graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-part-candidate-nodes 301 \
  --min-part-candidate-nodes-with-source-page-ids 301 \
  --min-part-candidate-nodes-with-part-number 301 \
  --min-part-families 1 \
  --min-table-cell-nodes 3090 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-lineage-quality-pass \
  --write-json
```

## Expected output

```text
TRACE-Net graph overlay PartCandidate property normalizer v1
 Status: GRAPH_OVERLAY_PART_PROPERTY_NORMALIZER_BUILT
 Quality status: PASS
 part_candidate_node_count: 301
 part_candidate_nodes_with_source_page_ids_count: 301
 part_candidate_nodes_with_part_number_count: 301
 part_candidate_missing_part_number_count: 0
 orphan_edge_count: 0
 retrieval_only_answer_allowed_count: 0
 source_truth_mutation_allowed_count: 0
```

## Output directory

```text
local_data/organization/trace_net/graph_overlay_part_property_normalizer/
```

Generated files include:

```text
trace_net_graph_overlay_part_property_normalizer_v1.json
trace_net_graph_overlay_part_property_normalizer_v1_nodes.jsonl
trace_net_graph_overlay_part_property_normalizer_v1_edges.jsonl
trace_net_graph_overlay_part_property_normalizer_v1_part_candidates.jsonl
trace_net_graph_overlay_part_property_normalizer_v1_summary.json
trace_net_graph_overlay_part_property_normalizer_v1_manifest.json
trace_net_graph_overlay_part_property_normalizer_v1_quality.json
trace_net_graph_overlay_part_property_normalizer_v1.md
trace_net_graph_overlay_part_property_normalizer_v1.html
```
