# TRACE-Net Engineering Context Pack Blueprint v1 Writer Fix

Fixes nested output directory failures in `trace_net_engineering_context_pack_blueprint_v1`.

The WebUI bridge preflight runs the context-pack blueprint stage under nested paths such as:

```text
local_data/organization/trace_net/engineering_webui_answer_server_v1_3_bridge_v1/sample_bridge_preflight/stage_reports/context_pack_blueprint/
```

Older local copies of the blueprint module can attempt to write JSONL or markdown sidecars before the parent directory exists. This patch makes `_write_json`, `_write_jsonl`, and `_write_markdown` parent-directory-safe and ensures `build_engineering_context_pack_blueprint` creates its output directory before writing sidecars.

Safety contract:

- no answer permission
- no LLM calls
- no retrieval execution
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes
