# TRACE-Net Calibrated Cascade Route Brain v35.3.1 where noted

Turns v35.2 route feature records into an operational cascade route manifest.

Inputs:
- `trace_net_cascade_route_feature_audit_v35_2.json`, or
- `trace_net_cascade_route_feature_records_v35_2.jsonl`

Outputs:
- calibrated cascade route report
- route manifest
- route decisions JSONL
- fishnet review queue JSONL

Safety contract:
- no answer permission
- no source-truth mutation
- no database writes
- no LLaVA/Gemma calls
- manual labels are calibration/evaluation labels, not proof authority


## v35.3.1 hotfix

This hotfix separates operational visual-context eligibility from fishnet review candidates. Secondary image routes are kept for review, but do not inflate the diagram/image precision metric or the expensive visual context dispatch set.
