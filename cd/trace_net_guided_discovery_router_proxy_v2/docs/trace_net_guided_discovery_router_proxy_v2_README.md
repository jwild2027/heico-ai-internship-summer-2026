# TRACE-Net Guided Discovery Router Proxy v2

This is a focused fix to the v1 router/proxy.

## Why v2 exists

The v1 router correctly classified exact part lookup as `normal_ask`, but it forwarded only:

```json
{"question":"Find part number 120-36833-001"}
```

The current normal TRACE-Net endpoint on `8014` rejected that payload with:

```text
Missing query or user message
```

v2 fixes the schema translation. For normal ask routes it now sends the user text in all compatible read-only shapes:

```json
{
  "query": "Find part number 120-36833-001",
  "question": "Find part number 120-36833-001",
  "messages": [{"role":"user","content":"Find part number 120-36833-001"}]
}
```

## Routes

- `GET /health`
- `POST /api/trace-net/router`
- `POST /v1/chat/completions`

## Safety contract

- Read-only proxy.
- No writes to Postgres.
- No writes to Qdrant.
- No writes to OpenSearch.
- No source-truth mutation.
- Guided discovery remains candidate-discovery-only.
