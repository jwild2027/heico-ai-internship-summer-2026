# TRACE-Net E2E WebUI Final Answer Endpoint v14

This phase serves v13 final-gated answers through an OpenAI-compatible local endpoint for Open WebUI.

The endpoint is artifact-backed and non-mutating. It reads the final answer gate report and exposes:

- `GET /health`
- `GET /v1/models`
- `POST /api/trace-net/ask`
- `POST /v1/chat/completions`

It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.

Open WebUI base URL from Docker:

```text
http://host.docker.internal:8017/v1
```

Windows/Git Bash test URL:

```text
http://127.0.0.1:8017/v1
```

Model:

```text
trace-net-e2e-webui-final-answer-endpoint-v14
```
