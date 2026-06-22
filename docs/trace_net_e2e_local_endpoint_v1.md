# TRACE-Net E2E Local Endpoint v1

This module exposes the passing artifact-backed TRACE-Net E2E API wrapper smoke as a tiny local HTTP endpoint.

It is intentionally lightweight and uses Python's standard library HTTP server. The goal is to make the E2E chain callable by Open WebUI before adding heavier Docker/FastAPI runtime wiring.

## Routes

- `GET /health`
- `GET /v1/models`
- `POST /api/trace-net/ask`
- `POST /v1/chat/completions`

## Safety contract

This endpoint returns smoke/API-wrapper response drafts from the passing E2E artifact chain. It does not grant source-truth authority, does not prove claims, does not mutate source truth, and does not write to Postgres, Qdrant, or OpenSearch.

## Example

```bash
python scripts/serve_trace_net_e2e_local_endpoint_v1.py \
  --e2e-api-wrapper-smoke local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json \
  --host 127.0.0.1 \
  --port 8014
```

```bash
curl -s http://127.0.0.1:8014/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"trace-net-e2e-local-endpoint-v1","messages":[{"role":"user","content":"Find part number 120-36833-001"}]}' \
  | python -m json.tool
```
