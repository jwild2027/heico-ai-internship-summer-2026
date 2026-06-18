# TRACE-Net Table Detector Overlay Review Pack v1

Builds a human-review packet from `trace_net_table_detector_overlay_audit_v1`.

This module is advisory only. It does not grant answer permission, prove claims,
mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Inputs

- `local_data/organization/trace_net/table_detector_overlay_audit/trace_net_table_detector_overlay_audit_v1.json`
- overlay PNGs referenced by the audit artifact

## Outputs

- `trace_net_table_detector_overlay_review_pack_v1.json`
- `trace_net_table_detector_overlay_review_pack_v1_cards.jsonl`
- `trace_net_table_detector_overlay_review_pack_v1_summary.json`
- `trace_net_table_detector_overlay_review_pack_v1_quality.json`
- `trace_net_table_detector_overlay_review_pack_v1_manifest.json`
- optional contact sheet PNGs under `contact_sheets/`

## Purpose

The prior detector parity and overlay audit showed disagreement between the
production morphology detector and the experiment estimator. This review pack
turns those overlay artifacts into a compact human review workflow so a reviewer
can decide whether the estimator is finding real table rules or text/noise.
