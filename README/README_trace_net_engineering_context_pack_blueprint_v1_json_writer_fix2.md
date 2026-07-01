# TRACE-Net Engineering Context Pack Blueprint v1 JSON Writer Fix 2

Focused fix for WebUI visual server preflight failures where the context-pack blueprint stage writes into a fresh nested directory such as:

```text
local_data/organization/trace_net/engineering_webui_answer_server_v1_3_bridge_v1_visual/sample_bridge_preflight/stage_reports/context_pack_blueprint/
```

The failing local traceback shows `_write_json` in `tiff/trace_net_engineering_context_pack_blueprint_v1.py` calling `path.write_text(...)` before ensuring `path.parent` exists. This patch makes the blueprint writer helpers parent-directory safe:

- `_write_json`
- `_write_jsonl`
- `_write_markdown`

It also includes directory-safety tests that build the blueprint into a clean nested `sample_bridge_preflight/stage_reports/context_pack_blueprint` directory.

Safety contract:

- no answer permission
- no LLM calls
- no retrieval execution
- no source-truth mutation
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
