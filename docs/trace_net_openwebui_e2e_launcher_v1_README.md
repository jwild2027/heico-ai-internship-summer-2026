# TRACE-Net Open WebUI E2E Launcher v1

Starts the TRACE-Net E2E endpoint and Open WebUI, smoke-tests both TRACE-Net native and OpenAI-compatible endpoints, then prints the exact Open WebUI connection settings.

Default behavior:
- starts existing `open-webui` container, or creates it if missing
- starts `scripts/serve_trace_net_e2e_local_endpoint_v1.py` on 0.0.0.0:8014 if not already running
- tests:
  - /health
  - /api/trace-net/ask
  - /v1/chat/completions
  - /v1/models if available
- holds the terminal open so the TRACE endpoint stays alive

Safety contract:
- launcher does not write Postgres/Qdrant/OpenSearch
- launcher does not mutate source truth
- launcher does not grant answer permission
- support containers are optional and not required for the current artifact-backed endpoint
