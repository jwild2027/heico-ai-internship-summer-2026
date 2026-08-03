# TRACE-Net H30 Cold Start and Validated Streaming Patch

## Scope

This patch fixes the first-message latency path without changing retrieval,
evidence selection, Self-RAG, CRAG, authority gating, or answer validation.

## Changes

1. Preloads `gemma4:26b` through Ollama's native `/api/generate` endpoint.
2. Uses a configurable one-hour default keep-alive (`TRACE_NET_GEMMA_KEEP_ALIVE=1h`).
3. Uses Ollama's native `/api/chat` endpoint for the final Gemma wording call.
4. Captures native Ollama timing fields: model load, prompt evaluation,
   generation, native time to first token, token counts, and tokens per second.
5. Measures TRACE-Net router/retrieval and total writer duration.
6. Adds immediate writer SSE headers, an initial role event, and heartbeat comments.
7. Makes the OpenWebUI bridge proxy upstream SSE instead of buffering a complete
   JSON response and manufacturing the entire stream afterward.
8. Keeps Gemma output buffered until TRACE-Net's existing whole-answer validator
   accepts it. Raw unvalidated model tokens are never sent to OpenWebUI.

## Safety

- No database or source-truth writes.
- No retrieval changes.
- No answer-permission changes.
- No raw unvalidated token exposure.
- Default keep-alive is one hour, not permanent.
