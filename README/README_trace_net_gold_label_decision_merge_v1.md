# TRACE-Net Gold Label Decision Merge v1

Merges auto-seeded route labels with human review CSV decisions to produce final gold route labels and an unresolved review queue.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission

Inputs:

- `trace_net_gold_label_auto_review_seed_v1.json`
- optional edited `high_priority_review.csv`
- optional edited `medium_priority_review.csv`
- optional edited `low_priority_auto_seeded_audit_sample.csv`
- optional extra review CSVs

Outputs:

- `trace_net_gold_label_decision_merge_v1.json`
- `trace_net_gold_label_decision_merge_v1_records.jsonl`
- `trace_net_gold_label_decision_merge_v1_final_labels.csv`
- `trace_net_gold_label_decision_merge_v1_unresolved_review_queue.csv`
- summary, quality, and markdown reports
