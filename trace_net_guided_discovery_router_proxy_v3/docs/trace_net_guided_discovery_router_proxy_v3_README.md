# TRACE-Net guided discovery router proxy v3

This patch adds `scripts/serve_trace_net_guided_discovery_router_proxy_v3.py`.

## Purpose

Router/proxy v3 keeps the v2 routing behavior and improves OpenAI-style chat output for the web UI.

- Weak/partial part-number questions route to guided discovery on `8016`.
- Ordinary TRACE-Net questions route to normal ask on `8014`.
- `/v1/chat/completions` now returns clean assistant-visible text for normal ask responses instead of dumping the full downstream JSON into `message.content`.
- The full TRACE-Net downstream payload remains available in `trace_net_payload`.

## Safety contract

- Read-only proxy.
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes/uploads.
- No source-truth mutation.
- Does not grant final-answer permission.

## Server command

```bash
python3 -B scripts/serve_trace_net_guided_discovery_router_proxy_v3.py \
  --host 127.0.0.1 \
  --port 8017 \
  --normal-base-url http://127.0.0.1:8014 \
  --guided-base-url http://127.0.0.1:8016 \
  --top-k 8 \
  --loose-top-k 8
```

## Smoke tests

Normal OpenAI-style chat:

```bash
curl -s http://127.0.0.1:8017/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"trace-net-router-proxy-v3","messages":[{"role":"user","content":"Find part number 120-36833-001"}]}' \
  | python3 -m json.tool
```

Guided discovery OpenAI-style chat:

```bash
curl -s http://127.0.0.1:8017/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"trace-net-router-proxy-v3","messages":[{"role":"user","content":"I only know the part starts with 24"}]}' \
  | python3 -m json.tool
```
