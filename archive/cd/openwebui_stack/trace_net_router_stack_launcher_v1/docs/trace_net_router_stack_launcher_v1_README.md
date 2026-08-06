# TRACE-Net Router Stack Launcher v1

This patch adds a one-command launcher for the local TRACE-Net web-UI stack.

It starts three existing read-only services:

1. `8014` normal TRACE-Net E2E endpoint.
2. `8016` guided candidate discovery endpoint.
3. `8017` router/proxy endpoint for web UI/OpenAI-compatible chat.

The launcher writes logs under:

```text
/data/trace_net_runs/router_stack_launcher_v1/logs/
```

and writes a manifest under:

```text
/data/trace_net_runs/router_stack_launcher_v1/trace_net_router_stack_launcher_v1_manifest.json
```

## Server command

```bash
cd ~/heico-ai-internship-summer-2026
source /home/jwild/rag-workspace/.venv/bin/activate

python3 -B scripts/launch_trace_net_router_stack_v1.py \
  --host 127.0.0.1 \
  --normal-port 8014 \
  --guided-port 8016 \
  --router-port 8017 \
  --artifact-root local_data/organization/trace_net \
  --output-root /data/trace_net_runs \
  --top-k 8 \
  --loose-top-k 8
```

Use `Ctrl+C` to stop all three services.

## Web UI target

```text
Base URL: http://127.0.0.1:8017/v1
Model: trace-net-router-proxy-v3
```

## Safety contract

This launcher only starts local read-only processes. It does not mutate source-truth artifacts and does not write to Postgres, Qdrant, or OpenSearch.
