# TRACE-Net Element-to-Graph Attachment Plan v1

Step 18 builds a read-only graph writeback plan from the TRACE-Net front-start and answer-safety artifacts.

It consumes page registry, structured table records, normalized rows/cells, visual regions/callouts, refined fishnet retry dispositions, embedding candidates, citation IDs, and trust/authority fields. It writes planned graph nodes and edges, but it does **not** mutate Postgres, Qdrant, TIFF/OCR files, trust records, or source truth.

## Purpose

Step 18 prepares graph attachments like:

```text
Page -> HAS_TABLE_ELEMENT -> TableElement
TableElement -> HAS_TABLE_ROW -> TableRow
TableRow -> HAS_TABLE_CELL -> TableCell
Page -> HAS_VISUAL_UNDERSTANDING -> VisualUnderstanding
VisualUnderstanding -> HAS_VISUAL_REGION -> VisualRegion
VisualUnderstanding -> HAS_CALLOUT_CANDIDATE -> CalloutCandidate
Page -> HAS_FISHNET_RETRY_PLAN -> FishnetRetryPlan
FishnetRetryPlan -> HAS_FISHNET_ACTION -> FishnetRetryAction
Page -> HAS_EVIDENCE_CANDIDATE -> EvidenceCandidate
EvidenceCandidate -> HAS_CITATION -> Citation
EvidenceCandidate -> HAS_TRUST_AUTHORITY -> TrustAuthority
```

The output is meant to be inspected and quality-checked before any later Postgres writeback.

## Safety contract

```text
writeback_mode = read_only_plan
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
```

Retrieval-only nodes cannot answer. Answer-support evidence must retain citation and trust/authority edges.

## Build

```bash
python scripts/build_trace_net_element_graph_attachment_plan_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --table-understanding local_data/organization/trace_net/table_understanding/trace_net_table_understanding_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --fishnet-retry-refined local_data/organization/trace_net/fishnet_retry_refined/trace_net_fishnet_retry_refinement_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --output-dir local_data/organization/trace_net/element_graph_attachment \
  --require-page-count 509 \
  --min-page-nodes 509 \
  --min-element-node-plans 1000 \
  --min-edge-plans 1000 \
  --min-table-node-plans 20 \
  --min-table-row-node-plans 100 \
  --min-table-cell-node-plans 100 \
  --min-visual-node-plans 100 \
  --min-fishnet-node-plans 509 \
  --min-citation-edge-plans 1 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-page-registry-quality-pass \
  --require-fishnet-refinement-quality-pass \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_element_graph_attachment_plan_v1_quality.py \
  --report-path local_data/organization/trace_net/element_graph_attachment/trace_net_element_graph_attachment_plan_v1.json \
  --require-page-count 509 \
  --min-page-nodes 509 \
  --min-element-node-plans 1000 \
  --min-edge-plans 1000 \
  --min-table-node-plans 20 \
  --min-table-row-node-plans 100 \
  --min-table-cell-node-plans 100 \
  --min-visual-node-plans 100 \
  --min-fishnet-node-plans 509 \
  --min-citation-edge-plans 1 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-page-registry-quality-pass \
  --require-fishnet-refinement-quality-pass \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/element_graph_attachment/
  trace_net_element_graph_attachment_plan_v1.json
  trace_net_element_graph_attachment_plan_v1_nodes.jsonl
  trace_net_element_graph_attachment_plan_v1_edges.jsonl
  trace_net_element_graph_attachment_plan_v1_records.jsonl
  trace_net_element_graph_attachment_plan_v1_summary.json
  trace_net_element_graph_attachment_plan_v1_manifest.json
  trace_net_element_graph_attachment_plan_v1_quality.json
  trace_net_element_graph_attachment_plan_v1.md
  trace_net_element_graph_attachment_plan_v1.html
```

## Next step

Step 19 should use this attachment plan to build a graph UI overlay or dry-run Postgres writeback validator before any mutation happens.
