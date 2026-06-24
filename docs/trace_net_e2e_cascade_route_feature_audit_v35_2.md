# TRACE-Net Cascade Route Feature Audit v35.2

This module computes cheap deterministic page-route features for stored manual TIFF pages and compares the baseline cascade prediction to the manually screened diagram-page label set.

It is an audit/calibration layer, not the final classifier.

Outputs:

- `trace_net_cascade_route_feature_audit_v35_2.json`
- `trace_net_cascade_route_feature_records_v35_2.jsonl`
- `trace_net_cascade_route_confusion_matrix_v35_2.json`
- `trace_net_cascade_route_feature_audit_v35_2.md`

Safety contract:

- no source-truth mutation
- no answer permission
- no database writes
- no LLaVA/Gemma calls
- manual labels are calibration/evaluation labels, not answer proof
