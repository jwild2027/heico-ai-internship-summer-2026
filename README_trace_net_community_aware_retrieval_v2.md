# TRACE-Net Community-Aware Retrieval v2

This module consumes the tightened Leiden navigation metadata bridge and produces retrieval-only community navigation hints for downstream hybrid retrieval.

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No claim-proof authority.
- Community and category signals remain navigation/ranking hints only.

## Inputs

- `local_data/organization/trace_net/leiden_navigation_metadata_bridge/trace_net_leiden_navigation_metadata_bridge_v1.json`
- `local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json`

## Outputs

- `local_data/organization/trace_net/community_aware_retrieval_v2/trace_net_community_aware_retrieval_v2.json`
- `local_data/organization/trace_net/community_aware_retrieval_v2/trace_net_community_aware_retrieval_v2_quality.json`
- `local_data/organization/trace_net/community_aware_retrieval_v2/trace_net_community_aware_retrieval_v2_records.jsonl`
- `local_data/organization/trace_net/community_aware_retrieval_v2/trace_net_community_aware_retrieval_v2_page_boosts.jsonl`

## Example

```bash
python scripts/build_trace_net_community_aware_retrieval_v2.py \
  --leiden-navigation-metadata-bridge local_data/organization/trace_net/leiden_navigation_metadata_bridge/trace_net_leiden_navigation_metadata_bridge_v1.json \
  --hybrid-v2-report local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json \
  --output-dir local_data/organization/trace_net/community_aware_retrieval_v2 \
  --min-queries 5 \
  --min-queries-with-navigation-hints 5 \
  --min-navigation-results 5 \
  --min-page-navigation-boosts 1 \
  --max-review-only-hints-used 0 \
  --max-low-confidence-hints-used 0 \
  --max-community-as-proof 0 \
  --max-category-as-proof 0 \
  --max-retrieval-only-answer-allowed 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-navigation-bridge-quality-pass \
  --require-hybrid-v2-quality-pass \
  --require-no-answer-permission \
  --quality
```
