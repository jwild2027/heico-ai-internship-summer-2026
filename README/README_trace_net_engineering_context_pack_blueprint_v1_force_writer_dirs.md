# TRACE-Net Context Pack Blueprint Force Writer Directory Fix

This focused patch replaces `tiff/trace_net_engineering_context_pack_blueprint_v1.py` with a runtime-safe writer version where `_write_json`, `_write_jsonl`, and `_write_markdown` all create parent directories before writing.

It also adds tests that directly exercise the exact WebUI sample preflight path:

`sample_bridge_preflight/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1.json`

Safety: no DB writes, no vector/search writes, no source-truth mutation, no answer permission.
