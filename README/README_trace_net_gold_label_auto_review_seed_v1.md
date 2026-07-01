# TRACE-Net Gold Label Auto Review Seed v1

Builds a conservative auto-review seed artifact from the visual-clamped gold-label review workbook.

The module does not mutate the source workbook. It creates a new JSON/JSONL/CSV/Markdown artifact where obvious high-confidence routes are prefilled into `auto_seeded_gold_route_label` and uncertain rows remain `human_review_required=true`.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no direct answering

Typical use:

```bash
python scripts/build_trace_net_gold_label_auto_review_seed_v1.py \
  --gold-label-workbook local_data/organization/trace_net/gold_label_review_workbook_visual_clamped/trace_net_gold_label_review_workbook_v1.json \
  --output-dir local_data/organization/trace_net/gold_label_auto_review_seed \
  --min-auto-seed-rows 100 \
  --quality
```
