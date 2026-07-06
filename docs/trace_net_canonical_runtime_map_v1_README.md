# TRACE-Net canonical runtime map v1

This module creates a repo-level runtime governance map before deeper cleanup or endpoint rewiring.

It answers five project questions:

1. What is the canonical pipeline?
2. Which major modules are active, support-only, superseded, archived, or backup snapshots?
3. Which OpenWebUI answer path is the current selected path?
4. Which existing Engram + Self-RAG + CRAG modules must be wired into that selected path?
5. Why backup/superseded files must not be moved yet.

## Current selected path

The selected current OpenWebUI answer path is:

`trace-net-page-context-v3-bridge`

Implementation:

- `scripts/serve_trace_net_openwebui_page_context_bridge_v1.py`
- `tiff/trace_net_openwebui_page_context_bridge_v1.py`
- `tiff/trace_net_page_context_pack_v3.py`

This is the path that recently passed native Gemma `/api/chat` visible-answer testing for page-context questions.

## Existing support modules to wire next

- `tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- `tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `tiff/trace_net_engineering_engram_core_v1.py`
- `tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- `tiff/trace_net_engineering_engram_self_rag_critic_v1.py`
- `tiff/trace_net_engineering_engram_crag_repair_v1.py`
- `tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py`

## Safety

This module is read-only with respect to source truth and databases.

It does not:

- move backup files;
- delete superseded files;
- write Postgres;
- write Qdrant;
- write OpenSearch;
- grant answer permission.

The cleanup policy stays `cleanup_allowed_now: false` until the current endpoint is wired to Engram + Self-RAG + CRAG and smoke/eval passes.
