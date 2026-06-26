# TRACE-Net Fishnet Router Hardening Policy v1

Read-only policy module that converts fishnet route review packet records into conservative router hardening recommendations.

## Purpose

The fishnet route review packet showed high-confidence cases where the current route manifest labels pages as `blank_candidate` or `image_visual`, while fishnet sees strong OCR-backed `normal_text` evidence. This module packages only the safest subset into `normal_text_review_promotion` recommendations.

## Safety contract

This module never authorizes route changes and never mutates the official route manifest.

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no route manifest writes
- route recommendations are review-only

## Inputs

- `local_data/organization/trace_net/fishnet_route_review_packet/trace_net_fishnet_route_review_packet_v1.json`

## Outputs

- `trace_net_fishnet_router_hardening_policy_v1.json`
- `trace_net_fishnet_router_hardening_policy_v1_records.jsonl`
- `trace_net_fishnet_router_hardening_policy_v1_summary.json`
- `trace_net_fishnet_router_hardening_policy_v1_quality.json`
- `trace_net_fishnet_router_hardening_policy_v1.md`

## Policy rule

A page is selected only when:

- current route is `blank_candidate` or `image_visual`
- fishnet route is `normal_text`
- fishnet confidence is at least the configured threshold
- OCR text length and OCR word boxes exceed configured thresholds
- fishnet did not already mark the page review-required
- no low-margin/table-text-tie reason appears
- no unsafe authority fields are present

Selected records remain review-only:

```json
{
  "recommendation_type": "normal_text_review_promotion",
  "recommendation_status": "review_required_before_route_manifest_change",
  "route_change_authorized": false,
  "route_manifest_write_allowed": false
}
```
