# TRACE-Net WebUI Self-RAG / CRAG Bridge v1 — directory fix

This focused fix preserves the existing bridge behavior while making the bridge safe on clean output directories.

## Fix

`trace_net_webui_self_rag_crag_bridge_v1` now pre-creates every nested stage report directory before calling the existing stage builders:

- `stage_reports/query_planner`
- `stage_reports/context_pack_blueprint`
- `stage_reports/context_pack_builder`
- `stage_reports/self_rag_check`
- `stage_reports/crag_retry_plan`

This fixes the observed WebUI bridge-server failure where `context_pack_blueprint` tried to write `trace_net_engineering_context_pack_blueprint_v1_records.jsonl` into a nested directory that did not exist yet.

## Safety

The bridge remains artifact-only and pre-answer:

- no Gemma call
- no final answer draft
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission

## Expected result

The standalone bridge and the WebUI v1.3 bridge-server sample preflight should now both reach:

- query planner used
- context pack builder used
- Self-RAG used
- CRAG evaluated as `used` or `skipped_not_needed`
- quality PASS
