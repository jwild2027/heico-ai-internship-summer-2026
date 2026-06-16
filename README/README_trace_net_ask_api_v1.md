# TRACE-Net Ask API v1

This patch adds a small, read-only HTTP API for exposing the current TRACE-Net final-gate and retrieval artifacts to a UI such as Open WebUI.

The API is intentionally conservative:

- It returns final answers only when a precomputed `final_answer_gate` artifact has `quality_status = PASS`, `final_answer_allowed = true`, and the query matches the artifact query.
- It can return retrieval-only ranked groups from the community-aware retrieval artifact.
- It never writes Postgres, Qdrant, OpenSearch, graph truth, source files, citations, or trust records.
- It exposes a minimal OpenAI-compatible `/v1/chat/completions` endpoint so Open WebUI can connect to it as a local model/API.

## Files

```text
tiff/trace_net_ask_api_v1.py
scripts/run_trace_net_ask_api_v1.py
scripts/check_trace_net_ask_api_v1_quality.py
tests/unit/test_trace_net_ask_api_v1.py
tests/unit/test_trace_net_ask_api_v1_quality.py
tests/unit/test_trace_net_ask_api_v1_script_imports.py
README_trace_net_ask_api_v1.md
```

## Test

```bash
python -m pytest \
  tests/unit/test_trace_net_ask_api_v1.py \
  tests/unit/test_trace_net_ask_api_v1_quality.py \
  tests/unit/test_trace_net_ask_api_v1_script_imports.py \
  -q
```

## Build config report only

```bash
python scripts/run_trace_net_ask_api_v1.py \
  --output-dir local_data/organization/trace_net/ask_api \
  --build-only \
  --quality
```

Quality check:

```bash
python scripts/check_trace_net_ask_api_v1_quality.py \
  --report-path local_data/organization/trace_net/ask_api/trace_net_ask_api_v1.json \
  --require-final-answer-quality-pass \
  --write-json
```

## Run server for Open WebUI

Bind to `0.0.0.0` so the Dockerized Open WebUI container can reach the host API via `host.docker.internal`:

```bash
python scripts/run_trace_net_ask_api_v1.py \
  --host 0.0.0.0 \
  --port 8012 \
  --output-dir local_data/organization/trace_net/ask_api
```

Health check from host:

```bash
curl -s http://localhost:8012/health | python -m json.tool
```

OpenAI-compatible model list:

```bash
curl -s http://localhost:8012/v1/models | python -m json.tool
```

TRACE-Net ask endpoint:

```bash
curl -s -X POST http://localhost:8012/api/trace-net/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Which pages discuss manual revision history?","answer_mode":"final-gate"}' \
  | python -m json.tool
```

OpenAI-compatible chat endpoint:

```bash
curl -s -X POST http://localhost:8012/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"trace-net-final-gate-v1","messages":[{"role":"user","content":"Which pages discuss manual revision history?"}]}' \
  | python -m json.tool
```

## Connect from Open WebUI

In Open WebUI, add an OpenAI-compatible connection with:

```text
Base URL: http://host.docker.internal:8012/v1
API key: leave blank, or set TRACE_NET_ASK_API_KEY and use that value
Model: trace-net-final-gate-v1
```

If the API is started with `--api-key`, Open WebUI must send that value as the API key.

## Safety boundary

This API is a bridge to existing TRACE-Net artifacts. It does not run the full pipeline dynamically yet. It does not convert Open WebUI's built-in RAG into source truth. It only exposes TRACE-Net-approved final-gate artifacts and retrieval-only groups.
