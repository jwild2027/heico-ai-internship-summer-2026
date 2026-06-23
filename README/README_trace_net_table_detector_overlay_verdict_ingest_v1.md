# TRACE-Net Table Detector Overlay Verdict Ingest v1

This stage normalizes human labels from the table detector overlay review pack.
It is read-only and does not grant answer permission or mutate source truth.

## Inputs

- `trace_net_table_detector_overlay_review_pack_v1.json`
- Optional CSV/JSON/JSONL verdict file

Verdict values:

- `UNREVIEWED`
- `ESTIMATOR_LINES_REAL_TABLE_RULES`
- `ESTIMATOR_LINES_TEXT_OR_NOISE`
- `MIXED_OR_UNCLEAR`

## Outputs

- `trace_net_table_detector_overlay_verdict_ingest_v1.json`
- `trace_net_table_detector_overlay_verdict_ingest_v1_cards.jsonl`
- `trace_net_table_detector_overlay_verdict_ingest_v1_summary.json`
- `trace_net_table_detector_overlay_verdict_template_v1.csv`
- `trace_net_table_detector_overlay_verdict_ingest_v1_quality.json`

## Safety

This artifact is advisory. It records which overlays were reviewed and whether
crop selection can be considered by later crop completeness guard logic. It does
not answer questions, prove claims, or write to Postgres/Qdrant/OpenSearch.
