# TRACE-Net E2E Image Visual Observer Route v34.1

v34.1 extends the image/visual route for uploaded images, scanned page images, diagrams, and callout-like visual pages.

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
→ Mermaid/JSON diagram draft card when requested
→ visual Self-RAG card
→ visual CRAG retry/fallback card
→ final-gated safe answer
```

## Endpoint

Model:

```text
trace-net-e2e-image-diagram-draft-llava-v34-1
```

Base URL from Windows:

```text
http://127.0.0.1:8030/v1
```

Base URL from Open WebUI Docker:

```text
http://host.docker.internal:8030/v1
```

## Open WebUI image use

The endpoint accepts OpenAI-compatible message content lists with image payloads, including `image_url` data URLs. In live mode it can call Ollama LLaVA using `/api/generate` with a base64 image array.

## Safety note

This route can say what it visually observes and can return a Mermaid/JSON diagram draft. It does not generate final technical drawings or proof-authority diagrams. It cannot prove what a part is, what a procedure requires, or what a manual relationship means unless another source-truth route confirms that evidence.

## Diagram draft behavior

When the user asks to turn an uploaded image into a diagram draft, the endpoint returns a guidance-only Mermaid diagram and structured diagram JSON in the trace payload. The draft is produced by the project endpoint from the LLaVA visual package, not by ChatGPT image generation.
