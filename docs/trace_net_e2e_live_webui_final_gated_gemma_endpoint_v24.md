# TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24

v24 exposes final-gated Gemma answers from the v23 final gate as an OpenAI-compatible local endpoint for Open WebUI.

## Contract

- Reads the v23 live LLM final gate artifact.
- Serves only final-gated answers that passed source-truth checks.
- Does not call Gemma at request time; v22 already generated drafts and v23 repaired/gated them.
- Source-truth evidence remains the only proof authority.
- Graph/Leiden and v2 summaries remain guidance only.
- Nearby OCR/table context is not direct proof for the user query.
- Does not scan raw 5TB source data, rebuild graph, rerun OCR, mutate source truth, or write to services.

## Endpoints

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

## Open WebUI

Use the Docker-facing base URL:

```text
http://host.docker.internal:8020/v1
```

Model:

```text
trace-net-e2e-live-final-gated-gemma-v24
```
