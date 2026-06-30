# TRACE-Net Image Route Endpoint Direct Fallback v1

This patch hardens the image-route OpenWebUI endpoint smoke wrapper. The preferred path remains the integrated `trace_net_fast_chat_runner_v1.py` subprocess. If the local runner subprocess/report discovery fails, the endpoint wrapper falls back to the same image route fast-chat adapter and image route multi-route quality gate that the runner uses, then writes a canonical `trace_net_fast_chat_runner_v1.json` report.

Safety remains unchanged: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.
