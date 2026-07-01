# TRACE-Net Fishnet Route Review Packet v1

Read-only review packet for fishnet/current-route disagreements.

## Purpose

This module consumes the fishnet route signal workbench and exports a compact
review packet. It includes all high-confidence disagreements, representative
route-pair examples, and optional review-required examples.

The packet is for human/visual review and route-hardening analysis only. It does
not modify any route manifest and does not authorize route changes.

## Inputs

- `local_data/organization/trace_net/fishnet_route_signal_workbench/trace_net_fishnet_route_signal_workbench_v1.json`
- Optional overlay directory, usually `local_data/organization/trace_net/fishnet_ocr_grid/overlays`

## Outputs

- `trace_net_fishnet_route_review_packet_v1.json`
- `trace_net_fishnet_route_review_packet_v1_records.jsonl`
- `trace_net_fishnet_route_review_packet_v1_summary.json`
- `trace_net_fishnet_route_review_packet_v1_quality.json`
- `trace_net_fishnet_route_review_packet_v1.md`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no route-change authorization

## Example

```bash
python scripts/build_trace_net_fishnet_route_review_packet_v1.py \
  --workbench-report local_data/organization/trace_net/fishnet_route_signal_workbench/trace_net_fishnet_route_signal_workbench_v1.json \
  --output-dir local_data/organization/trace_net/fishnet_route_review_packet \
  --overlays-dir local_data/organization/trace_net/fishnet_ocr_grid/overlays \
  --high-confidence-limit 50 \
  --representative-per-pair 5 \
  --review-required-limit 25 \
  --quality
```
