# TRACE-Net Route Unresolved Retry/Probe v1

This module reads the four-route validator runner output and retries only pages
that remain `validator_gated_unresolved`.

It is designed for scale: no human review is required. Pages that pass a safe
automatic retry probe are promoted to a final validated operational route. Pages
that still fail remain source-traceable and blocked from retrieval.

## Inputs

- `local_data/organization/trace_net/route_validator_runner/trace_net_route_validator_runner_v1.json`

## Outputs

- `trace_net_route_unresolved_retry_probe_v1.json`
- `trace_net_route_unresolved_retry_probe_v1_records.jsonl`
- `trace_net_route_unresolved_retry_probe_v1_records.csv`
- `trace_net_route_unresolved_retry_probe_v1_validated_records.csv`
- `trace_net_route_unresolved_retry_probe_v1_unresolved_records.csv`
- `trace_net_route_unresolved_retry_probe_v1_summary.json`
- `trace_net_route_unresolved_retry_probe_v1_quality_check.json`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
