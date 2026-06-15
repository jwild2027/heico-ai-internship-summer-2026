# TRACE-Net Retrieval Critic v1

This module is the first small Self-RAG-style critic layer for TRACE-Net.

It reads Hybrid Retrieval v2 output and emits one read-only critic record per query. The critic can recommend actions such as:

- `run_dynamic_final_gate_for_query`
- `keep_retrieval_only_and_run_citation_authority_or_review`
- `run_or_expand_exact_search`
- `expand_semantic_search_or_context_profiles`
- `abstain_or_expand_retrieval`
- `return_final_gate_answer`

The critic cannot answer directly, cannot prove claims, and cannot mutate source truth.

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_retrieval_critic_v1.py \
  tests/unit/test_trace_net_retrieval_critic_v1_quality.py \
  tests/unit/test_trace_net_retrieval_critic_v1_script_imports.py \
  -q
```

## Build

```bash
python scripts/build_trace_net_retrieval_critic_v1.py \
  --hybrid-v2-report local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json \
  --dynamic-final-gate local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json \
  --opensearch-adapter local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --category-aware-leiden-overlay local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json \
  --feedback-memory local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --output-dir local_data/organization/trace_net/retrieval_critic \
  --min-critic-records 5 \
  --min-queries 5 \
  --require-hybrid-v2-quality-pass \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_retrieval_critic_v1_quality.py \
  --report-path local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json \
  --min-critic-records 5 \
  --min-queries 5 \
  --require-hybrid-v2-quality-pass \
  --write-json
```

## Safety contract

- Retrieval critic output is advisory only.
- It does not write Postgres, Qdrant, or OpenSearch.
- It does not answer directly.
- It does not prove claims.
- Feedback, communities, and categories remain non-proof signals.
