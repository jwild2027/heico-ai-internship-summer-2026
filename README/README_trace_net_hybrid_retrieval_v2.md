# TRACE-Net Hybrid Retrieval v2

Hybrid Retrieval v2 is a read-only, live-ready retrieval planner that combines:

- semantic groups from Hybrid Retrieval Simulation v1;
- exact/keyword matches over the safe OpenSearch Adapter v1 document set;
- Category-Aware Leiden Overlay page/community hints;
- sanitized Feedback Memory as advisory ranking only.

It does not require a running OpenSearch server yet. It locally scans the safe
OpenSearch document artifact, which lets us test hybrid ranking before the
OpenSearch Loader Smoke module is available.

Safety contract:

- retrieval groups cannot answer directly;
- retrieval groups cannot prove claims;
- feedback, communities, and categories are not proof;
- no Postgres, Qdrant, OpenSearch, graph, source, citation, or answer writes;
- source truth mutation is not allowed.

## Build

```bash
python scripts/build_trace_net_hybrid_retrieval_v2.py \
  --hybrid-report local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json \
  --opensearch-adapter local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --community-aware-retrieval local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json \
  --category-aware-leiden-overlay local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json \
  --feedback-memory local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --output-dir local_data/organization/trace_net/hybrid_retrieval_v2 \
  --min-queries 5 \
  --min-queries-with-results 5 \
  --min-groups 5 \
  --min-exact-hit-groups 1 \
  --min-semantic-groups 1 \
  --require-opensearch-quality-pass \
  --require-hybrid-quality-pass \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_hybrid_retrieval_v2_quality.py \
  --report-path local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json \
  --min-queries 5 \
  --min-queries-with-results 5 \
  --min-groups 5 \
  --min-exact-hit-groups 1 \
  --min-semantic-groups 1 \
  --require-opensearch-quality-pass \
  --require-hybrid-quality-pass \
  --write-json
```

## Outputs

- `trace_net_hybrid_retrieval_v2.json`
- `trace_net_hybrid_retrieval_v2_results.jsonl`
- `trace_net_hybrid_retrieval_v2_groups.jsonl`
- `trace_net_hybrid_retrieval_v2_summary.json`
- `trace_net_hybrid_retrieval_v2_quality.json`
- `trace_net_hybrid_retrieval_v2_manifest.json`
- `trace_net_hybrid_retrieval_v2.md`
