# TRACE-Net WebUI Self-RAG/CRAG Bridge v1 Stage Directory Fix 2

This focused fix pre-creates all nested `stage_reports/*` folders before invoking stage builders in `trace_net_webui_self_rag_crag_bridge_v1`.

## Why

The visual-context patch introduced or re-exposed a clean-output regression: the bridge computed stage output directories but did not call `mkdir(parents=True, exist_ok=True)` before passing them to stage builders. Tests that monkeypatch stage builders to write without creating directories correctly failed.

## Safety

This is artifact-path plumbing only. It does not call Gemma, does not draft an answer, does not write Postgres/Qdrant/OpenSearch, does not mutate source truth, and does not grant answer permission.
