# TRACE-Net Table Geometry Review Bridge v1

This module converts low-confidence/advisory `trace_net_table_line_geometry_v1` cards into human-review task records.

It is a review-workflow bridge, not a repair engine and not an answer engine.

## Inputs

- `local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`

## Outputs

- `local_data/organization/trace_net/table_geometry_review_bridge/trace_net_table_geometry_review_bridge_v1.json`
- `trace_net_table_geometry_review_bridge_v1_tasks.jsonl`
- `trace_net_table_geometry_review_bridge_v1_summary.json`
- `trace_net_table_geometry_review_bridge_v1_quality.json`
- `trace_net_table_geometry_review_bridge_v1_manifest.json`

## Safety contract

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority
- Human-review tasks are advisory and require separate promotion/writeback gates

## Build

```bash
python scripts/build_trace_net_table_geometry_review_bridge_v1.py \
  --table-line-geometry local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json \
  --output-dir local_data/organization/trace_net/table_geometry_review_bridge \
  --min-source-cards 1 \
  --min-review-tasks 1 \
  --max-unsafe-source-cards 0 \
  --max-unsafe-review-tasks 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-source-quality-pass \
  --require-no-answer-permission \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_table_geometry_review_bridge_v1_quality.py \
  --report-path local_data/organization/trace_net/table_geometry_review_bridge/trace_net_table_geometry_review_bridge_v1.json \
  --min-source-cards 1 \
  --min-review-tasks 1 \
  --max-unsafe-source-cards 0 \
  --max-unsafe-review-tasks 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-source-quality-pass \
  --require-no-answer-permission \
  --write-json
```

## Review task behavior

A table geometry card becomes a review task when any of these are true:

- `review_required` is true
- it has `review_flags`
- `merged_cell_candidate_count > 0`
- `geometry_confidence` is below the configured threshold
- image/ruling-line detection is unavailable

Each task preserves page/table IDs, source page IDs, domain validation counts, geometry confidence, review flags, and recommended actions while forcing all answer/proof/source-mutation authority flags to false.
