# TRACE-Net Table Detector Overlay Audit v1

Read-only diagnostic module for Step 2 of the TRACE-Net table morphology route.

This module compares detector disagreement cards from
`trace_net_table_margin_detector_parity_v1` and creates audit records plus
optional PNG overlays.  The goal is to inspect whether the experiment estimator
is finding real table ruling lines or accidentally counting text strokes/noise.

## Inputs

- `local_data/organization/trace_net/table_margin_detector_parity/trace_net_table_margin_detector_parity_v1.json`
- `local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json`
- resolved page images under `--image-root`

## Outputs

- `trace_net_table_detector_overlay_audit_v1.json`
- `trace_net_table_detector_overlay_audit_v1_cards.jsonl`
- `trace_net_table_detector_overlay_audit_v1_summary.json`
- `trace_net_table_detector_overlay_audit_v1_quality.json`
- `trace_net_table_detector_overlay_audit_v1_manifest.json`
- optional PNG overlays under `overlays/`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
- advisory diagnostics only

## Example

```bash
python scripts/build_trace_net_table_detector_overlay_audit_v1.py \
  --margin-detector-parity local_data/organization/trace_net/table_margin_detector_parity/trace_net_table_margin_detector_parity_v1.json \
  --table-bbox-resolver local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_detector_overlay_audit \
  --max-overlay-cards 20 \
  --min-audit-cards 20 \
  --min-detector-disagreement-cards 1 \
  --min-overlay-ready-cards 1 \
  --max-unsafe-audit-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-margin-detector-parity-quality-pass \
  --require-table-bbox-resolver-quality-pass \
  --require-no-answer-permission \
  --quality
```
