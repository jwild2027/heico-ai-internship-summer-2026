# TRACE-Net Graph Query API v1.1

Read-only API wrapper for controlled graph lookup with optional evidence enrichment.

Default routes return the organization-graph view from Graph Query Helper v1.
Adding `include_evidence=true` returns the Graph Query Evidence Enrichment v1 view, which merges organization graph pages with OpenSearch exact evidence, Hybrid Retrieval v2 groups, Leiden navigation hints, Dublin Core source identity, and claim-entailment review signals.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

Core routes:

- `GET /health`
- `GET /graph/routes`
- `GET /graph/enrichment/summary`
- `GET /graph/part/{part_number}/sources?include_evidence=true`
- `GET /graph/page/{page_id}?include_evidence=true`
- `GET /graph/ata/{ata_code}/pages?include_evidence=true`
- `POST /graph/query`

Example:

```bash
python scripts/run_trace_net_graph_query_api_v1_1.py \
  --graph-query-helper local_data/organization/trace_net/graph_query_helper/trace_net_graph_query_helper_v1.json \
  --graph-query-evidence-enrichment local_data/organization/trace_net/graph_query_evidence_enrichment/trace_net_graph_query_evidence_enrichment_v1.json \
  --output-dir local_data/organization/trace_net/graph_query_api_v1_1 \
  --host 0.0.0.0 \
  --port 8016 \
  --require-helper-quality-pass \
  --require-enrichment-quality-pass \
  --require-no-answer-permission \
  --quality
```
