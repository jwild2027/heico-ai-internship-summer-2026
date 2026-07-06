# TRACE-Net Dry Run Loader Planner v1

Prepares no-write loader manifests from the four-route storage gate.

Inputs:

- `local_data/organization/trace_net/four_route_storage_gate/trace_net_four_route_storage_gate_v1.json`

Outputs:

- Full planner JSON
- All planner records JSONL
- Postgres graph dry-run plan JSONL
- Qdrant dry-run plan JSONL
- OpenSearch dry-run plan JSONL
- Blocked loader records CSV

Safety contract:

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- Dry-run plans only
