# TRACE-Net OpenWebUI Full Stack v1

OpenWebUI should connect to one front door:

```text
OpenWebUI -> 8017 router/proxy
```

The router fans out internally:

```text
8017 router/proxy
  -> 8014 normal exact/OCR/table route
  -> 8016 guided discovery route
  -> Gemma confirmed image visual route inside 8017
```

Do **not** connect OpenWebUI separately to each route. That makes the UI messy and
lets users pick the wrong internal tool.

## OpenWebUI connection

Same host:

```text
Base URL: http://127.0.0.1:8017/v1
API key: trace-net-local
Model: trace-net-router-proxy-v6-gemma-visual-v1
```

If OpenWebUI runs inside Docker, use the host-reachable address, often:

```text
http://host.docker.internal:8017/v1
```

or on Linux:

```text
http://172.17.0.1:8017/v1
```

## Scripts

- `launch_trace_net_openwebui_full_stack_v1.py`
- `check_trace_net_openwebui_connection_v1.py`

## Safety

The visual route remains retrieval guidance only. It does not grant answer
permission, and it does not write to Postgres/Qdrant/OpenSearch.
