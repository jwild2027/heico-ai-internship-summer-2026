# TRACE-Net Human Review Queue Table Geometry Integration v1

This module merges the PASS `trace_net_table_geometry_review_bridge_v1` artifact into the main `trace_net_human_review_queue_v1` artifact.

## Purpose

The Table Line Geometry and Table Geometry Review Bridge stages identify low-confidence table geometry, missing image-line detection, part-number table review needs, row/column boundary uncertainty, and cell assignment review needs. This integration stage converts those bridge tasks into the main Human Review Queue schema so they appear alongside other TRACE-Net review tasks.

## Inputs

- `local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json` optional existing base queue
- `local_data/organization/trace_net/table_geometry_review_bridge/trace_net_table_geometry_review_bridge_v1.json`

## Outputs

Written to `local_data/organization/trace_net/human_review_queue/`:

- `trace_net_human_review_queue_v1.json`
- `trace_net_human_review_queue_v1_tasks.jsonl`
- `trace_net_human_review_queue_v1_summary.json`
- `trace_net_human_review_queue_v1_quality.json`
- `trace_net_human_review_queue_table_geometry_integration_v1_quality.json`
- `trace_net_human_review_queue_table_geometry_integration_v1_manifest.json`

## Safety contract

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority
- Human-review tasks are advisory only

## Example

```bash
python scripts/build_trace_net_human_review_queue_table_geometry_integration_v1.py \
  --human-review-queue local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json \
  --table-geometry-review-bridge local_data/organization/trace_net/table_geometry_review_bridge/trace_net_table_geometry_review_bridge_v1.json \
  --output-dir local_data/organization/trace_net/human_review_queue \
  --min-review-tasks 1 \
  --min-table-geometry-review-tasks 20 \
  --require-table-geometry-bridge-quality-pass \
  --require-no-answer-permission \
  --quality
```
