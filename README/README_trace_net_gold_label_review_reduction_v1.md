# TRACE-Net Gold Label Review Reduction v1

Builds review-priority outputs from the conservative auto-review seed artifact.

Inputs:

- `trace_net_gold_label_auto_review_seed_v1.json`

Outputs:

- `high_priority_review.csv`
- `medium_priority_review.csv`
- `low_priority_auto_seeded_audit_sample.csv`
- `route_grouped_review.xlsx`
- `page_range_review_plan.md`
- JSON/JSONL/summary/quality reports

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.
