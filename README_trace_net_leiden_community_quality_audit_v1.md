# TRACE-Net Leiden Community Quality Audit v1

Read-only audit for Leiden/community artifacts.

This module checks that Leiden communities remain advisory navigation/ranking
context and do not become answer proof. It also surfaces community hygiene risks:
missing labels, missing category summaries, over-large communities, mixed-category
communities, and policy leaks such as `can_answer_directly` or `can_prove_claims`.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

Typical build:

```bash
python scripts/build_trace_net_leiden_community_quality_audit_v1.py \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --category-aware-leiden-overlay local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json \
  --graph-ui-community-overlay local_data/organization/trace_net/graph_ui_community_overlay/trace_net_graph_ui_community_overlay_v1.json \
  --output-dir local_data/organization/trace_net/leiden_community_quality_audit \
  --require-page-count 509 \
  --min-communities 229 \
  --min-audit-records 229 \
  --min-page-coverage 509 \
  --require-leiden-quality-pass \
  --require-category-overlay-quality-pass \
  --require-no-orphan-edges \
  --quality
```
