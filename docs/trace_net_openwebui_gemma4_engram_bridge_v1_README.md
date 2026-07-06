# TRACE-Net Open WebUI Gemma4 Engram Bridge v1

This is the newer Open WebUI endpoint for interactive testing.

It is different from the old `trace-net-e2e-local-endpoint-v1` smoke endpoint:
- old endpoint was artifact-smoke / canned-match oriented
- this bridge dynamically retrieves source-trace evidence cards from TRACE-Net artifacts
- calls local Ollama `gemma4:26b`
- injects Engram behavior guidance
- supports OpenAI-compatible `/v1/chat/completions`
- supports native `/api/trace-net/ask`
- includes `/v1/models`

Safety contract:
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes
- answer permission remains false
- Engram and summaries are guidance only, not proof
