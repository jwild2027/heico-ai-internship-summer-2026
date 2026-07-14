# TRACE-Net Demo Stack Launcher v1

Starts the local demo stack in one terminal:

```text
8014 = normal ask endpoint
8016 = guided candidate discovery endpoint
8017 = main router/proxy with gated visual v1.1
```

## Run

```bash
python -B scripts/serve_trace_net_demo_stack_launcher_v1.py
```

The launcher writes logs here by default:

```text
local_data/organization/trace_net/demo_stack_launcher_v1_runtime/
```

## Open WebUI

Use:

```text
Base URL: http://127.0.0.1:8017/v1
Model: trace-net-router-proxy-v6-gated-visual-v1-1
API key: anything
```

If Open WebUI is in Docker:

```text
Base URL: http://host.docker.internal:8017/v1
```

## Demo prompts

```text
Show figure references for passenger seat assembly diagram
I only know the part starts with 24
Find part number 120-36833-001
```

## Safety

The launcher only starts local services and writes runtime logs/summary files.
It does not mutate source truth and does not write to Postgres, Qdrant, or
OpenSearch.
