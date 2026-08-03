# TRACE-Net Guided Discovery Router Proxy v1

This patch adds one read-only router/proxy endpoint for the web UI.

It routes:

- normal TRACE-Net questions to the existing E2E ask endpoint on `8014`
- weak or partial part-number questions to guided candidate discovery on `8016`

The router exists so a UI can call one endpoint without knowing whether the user asked a normal evidence-backed question or a guided candidate discovery question.

## Endpoints

Start the proxy on `8017`.

- `GET /health`
- `GET /api/trace-net/router/health`
- `POST /api/trace-net/router`
- `POST /v1/chat/completions`

## Safety contract

The router is read-only. It does not write to Postgres, Qdrant, OpenSearch, or source-truth artifacts. Guided discovery responses remain candidate-discovery-only and should keep `final_answer_allowed=false`.

## Routing behavior

Examples routed to guided discovery:

- `I am looking for a part that starts with numbers 2 and 4 but I do not have the rest`
- `I only know the part starts with 24`
- `The part contains 24 and looked like a bolt`

Examples routed to normal ask:

- `Find part number 120-36833-001`
- `What is the ATA number for this manual?`

The request can override routing with `mode`:

- `mode: "guided"`
- `mode: "normal"`

## Server command

```bash
python3 -B scripts/serve_trace_net_guided_discovery_router_proxy_v1.py \
  --host 127.0.0.1 \
  --port 8017 \
  --normal-base-url http://127.0.0.1:8014 \
  --guided-base-url http://127.0.0.1:8016 \
  --top-k 8 \
  --loose-top-k 8
```

## Curl examples

```bash
curl -s http://127.0.0.1:8017/api/trace-net/router \
  -H "Content-Type: application/json" \
  -d '{"question":"I am looking for a part that starts with numbers 2 and 4 but I do not have the rest"}' \
  | python3 -m json.tool
```

```bash
curl -s http://127.0.0.1:8017/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"trace-net-router-proxy-v1","messages":[{"role":"user","content":"I only know the part starts with 24"}]}' \
  | python3 -m json.tool
```
