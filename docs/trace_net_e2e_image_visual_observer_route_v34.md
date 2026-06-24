# TRACE-Net E2E Image Visual Observer Route v34

v34 introduces the first image/visual route for uploaded images, scanned page images, diagrams, and callout-like visual pages.

## Contract

- LLaVA observations are guidance only.
- Image observations are not source-truth proof.
- Source-truth confirmation is required before factual part/manual claims.
- Low-confidence visual observations require human review or crop/retry.
- This stage does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch.

## Route shape

```text
image upload / page image / crop
→ image quality card
→ LLaVA visual observer card
→ visual Self-RAG card
→ visual CRAG retry/fallback card
→ final-gated safe answer
```

## Endpoint

Model:

```text
trace-net-e2e-image-visual-observer-llava-v34
```

Base URL from Windows:

```text
http://127.0.0.1:8029/v1
```

Base URL from Open WebUI Docker:

```text
http://host.docker.internal:8029/v1
```

## Open WebUI image use

The endpoint accepts OpenAI-compatible message content lists with image payloads, including `image_url` data URLs. In live mode it can call Ollama LLaVA using `/api/generate` with a base64 image array.

## Safety note

This route can say what it visually observes. It cannot prove what a part is, what a procedure requires, or what a manual relationship means unless another source-truth route confirms that evidence.
