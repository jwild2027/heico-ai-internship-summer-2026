# TRACE-Net Hybrid Retrieval v3

Hybrid Retrieval v3 is a read-only, CRAG-aware retrieval control layer for TRACE-Net.
It consumes the PASS-certified Hybrid Retrieval v2 output, the PASS-certified
Corrective Retrieval Planner v1 output, and can now optionally consume the
PASS-certified live OpenSearch exact-search index as a read-only retrieval channel.

## Purpose

Hybrid Retrieval v3 ranks retrieval groups, attaches safe corrective-routing
metadata, and labels groups as routing-ready or review-required. With live
OpenSearch enabled, it also performs read-only exact searches against the live
`trace_net_safe_search_v1` index and attaches exact hits to the relevant groups.

It still does **not** answer user questions. Final-answer authority remains with
the final gate / final-return policy layer.

## Inputs

Default inputs live under `local_data/organization/trace_net/`:

- `hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json`
- `corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1.json`
- `graph_query_evidence_enrichment/trace_net_graph_query_evidence_enrichment_v1.json`
- `opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json`
- `opensearch_live_loader/trace_net_opensearch_live_loader_v1.json`
- `qdrant_page_retrieval_profiles_ollama_bge_m3/trace_net_page_retrieval_profiles_qdrant_v1_quality.json`

Optional live exact-search inputs:

- OpenSearch URL: `http://localhost:9200`
- Index: `trace_net_safe_search_v1`

## Outputs

Default outputs are written to:

`local_data/organization/trace_net/hybrid_retrieval_v3/`

Files:

- `trace_net_hybrid_retrieval_v3.json`
- `trace_net_hybrid_retrieval_v3_results.jsonl`
- `trace_net_hybrid_retrieval_v3_groups.jsonl`
- `trace_net_hybrid_retrieval_v3_summary.json`
- `trace_net_hybrid_retrieval_v3_quality.json`
- `trace_net_hybrid_retrieval_v3_manifest.json`

## Safety contract

Hybrid Retrieval v3 is retrieval/routing only:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes; live OpenSearch use is read-only search
- no source-truth mutation
- no answer permission
- no claim-proof authority
- community/category/feedback/corrective actions remain advisory only
- live OpenSearch exact hits remain retrieval-only evidence-routing signals

## Commands

Build with live OpenSearch exact hits:

```bash
python scripts/build_trace_net_hybrid_retrieval_v3.py \
  --hybrid-v2 local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json \
  --corrective-planner local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1.json \
  --graph-query-evidence-enrichment local_data/organization/trace_net/graph_query_evidence_enrichment/trace_net_graph_query_evidence_enrichment_v1.json \
  --opensearch-loader-smoke local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json \
  --opensearch-live-loader local_data/organization/trace_net/opensearch_live_loader/trace_net_opensearch_live_loader_v1.json \
  --enable-live-opensearch \
  --opensearch-url http://localhost:9200 \
  --opensearch-index-name trace_net_safe_search_v1 \
  --max-live-exact-hits-per-query 10 \
  --qdrant-page-profile-quality local_data/organization/trace_net/qdrant_page_retrieval_profiles_ollama_bge_m3/trace_net_page_retrieval_profiles_qdrant_v1_quality.json \
  --output-dir local_data/organization/trace_net/hybrid_retrieval_v3 \
  --min-live-exact-hit-groups 1 \
  --require-opensearch-live-loader-quality-pass \
  --quality
```

Quality check:

```bash
python scripts/check_trace_net_hybrid_retrieval_v3_quality.py \
  --report-path local_data/organization/trace_net/hybrid_retrieval_v3/trace_net_hybrid_retrieval_v3.json \
  --min-live-exact-hit-groups 1 \
  --require-opensearch-live-loader-quality-pass \
  --write-json
```
