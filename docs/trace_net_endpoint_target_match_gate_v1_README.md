# TRACE-Net Endpoint Target Match Gate v1

Adds a read-only proxy endpoint that sits in front of the existing TRACE-Net local endpoint.

## Why

The fixed-50 target citation validator found one off-target citation case: a query for `DF250040-501` received citations for `120-36833-*`. Gemma answered safely, but the raw endpoint response still promoted unrelated citations.

## Behavior

- Explicit part targets are extracted deterministically from the user query.
- If the downstream endpoint returns citations and none match the requested target, the proxy returns `AUDIT_ONLY_TARGET_NOT_FOUND` with zero citations.
- If citations match the requested target, the response passes through unchanged except for target-gate metadata.
- If no citations are returned, the response passes through unchanged except for target-gate metadata.

## Safety

This script is read-only. It does not call Ollama, write to Postgres/Qdrant/OpenSearch, upload to OpenSearch, or mutate source truth.

## Run

Keep the original TRACE-Net endpoint running on port `8014`, then start the target gate proxy on port `8015`:

```bash
python3 -B scripts/serve_trace_net_e2e_local_endpoint_target_gate_v1.py \
  --host 127.0.0.1 \
  --port 8015 \
  --base-url http://127.0.0.1:8014
```

Point fixed-50 runner at:

```text
http://127.0.0.1:8015/api/trace-net/ask
```
