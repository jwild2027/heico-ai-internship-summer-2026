# TRACE-Net Corrective Retrieval Planner v1

Read-only CRAG-style planner for TRACE-Net.

This module reads existing TRACE-Net retrieval, trace, graph, exact-search, Qdrant, and audit artifacts. It diagnoses weak retrieval and review cases, then emits safe correction actions such as graph-path expansion, OpenSearch exact search, reranking, vision/content review, and human review.

It does not answer directly, prove claims, write to Postgres/Qdrant/OpenSearch, or mutate source truth.

## Inputs

- Page Retrieval Large Eval v2
- AI Trace Pack v1
- Graph Query Evidence Enrichment v1
- OpenSearch Loader Smoke v1
- Qdrant page profile quality JSON
- optional TIFF Content Audit v1

## Outputs

- `trace_net_corrective_retrieval_planner_v1.json`
- `trace_net_corrective_retrieval_planner_v1_quality.json`
- `trace_net_corrective_retrieval_planner_v1_records.jsonl`
- `trace_net_corrective_retrieval_planner_v1_summary.md`

## Safety contract

Every record is retrieval-only and has:

```text
can_answer_directly: false
can_prove_claims: false
source_truth_mutation_allowed: false
postgres_write_attempt_count: 0
qdrant_write_attempt_count: 0
opensearch_write_attempt_count: 0
```
