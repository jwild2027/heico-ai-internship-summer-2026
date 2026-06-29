# TRACE-Net Anchor-Aware Graph/Leiden Expander v1

This module sits after `trace_net_answer_context_anchor_injector_v1`.

It uses proven direct exact-match anchors as the center of graph/Leiden expansion, then annotates nearby/family/support records with relation roles such as:

- `direct_exact_match_anchor`
- `exact_reference_anchor`
- `same_anchor_community_variant`
- `same_anchor_page_variant`
- `same_anchor_leiden_community_neighbor`
- `nearby_anchor_page_neighbor`
- `superseded_direct_candidate`

Safety contract:

- Dry-run only.
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- Graph and Leiden may rank nearby evidence, but they never prove exact part identity by themselves.

## Build

```bash
python scripts/build_trace_net_anchor_aware_graph_leiden_expander_v1.py \
  --anchor-injector local_data/organization/trace_net/answer_context_anchor_injector_gemma4_native_001/trace_net_answer_context_anchor_injector_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json \
  --community-aware-retrieval local_data/organization/trace_net/community_aware_retrieval_v2/trace_net_community_aware_retrieval_v2.json \
  --output-dir local_data/organization/trace_net/anchor_aware_graph_leiden_expander_gemma4_native_001 \
  --max-records 40 \
  --require-source-quality-pass \
  --require-anchor-communities \
  --quality
```

## Check

```bash
python scripts/check_trace_net_anchor_aware_graph_leiden_expander_v1_quality.py \
  --report-path local_data/organization/trace_net/anchor_aware_graph_leiden_expander_gemma4_native_001/trace_net_anchor_aware_graph_leiden_expander_v1.json \
  --write-json \
  --min-records 1 \
  --min-direct-anchors 8 \
  --min-anchor-communities 1 \
  --min-same-anchor-relations 1 \
  --min-citations 8 \
  --min-prompt-chars 500 \
  --max-violation-records 0 \
  --require-source-quality-pass \
  --require-anchor-aware-prompt \
  --require-no-human-review-required \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts
```
