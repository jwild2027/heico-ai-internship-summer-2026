# TRACE-Net Route Dispatch Processor Contract v1

Builds the downstream processor contract from the passing route-dispatch stack.

Inputs:

- `trace_net_route_dispatch_manifest_v1.json`
- `trace_net_route_dispatch_coverage_audit_v1.json`
- `trace_net_route_dispatch_warning_triage_v1.json`

Outputs:

- `trace_net_route_dispatch_processor_contract_v1.json`
- `trace_net_route_dispatch_processor_contract_v1_quality.json`
- `table_allowed_pages.json`
- `image_visual_allowed_pages.json`
- `normal_text_allowed_pages.json`
- `blank_candidate_pages.json`
- `review_required_pages.json`

Safety contract:

- no answer permission
- no direct answer claims
- no source-truth mutation
- no database/vector/search writes
