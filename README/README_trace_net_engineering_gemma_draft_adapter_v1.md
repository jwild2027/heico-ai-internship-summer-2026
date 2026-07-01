# TRACE-Net Engineering Gemma Draft Adapter v1.1

Converts Self-RAG-approved engineering draft packets into local Gemma/Ollama or OpenAI-compatible request payloads.

v1.1 adds Ollama thinking control:
- `--ollama-think false` by default
- writes top-level `"think": false` into Ollama `/api/chat` request payloads
- records `ollama_think` in adapter config and quality reports

Why:
Gemma4 is a thinking-capable model. If thinking output is separated from final `message.content`, the draft runner correctly treats empty final content as not ready for final gate review. Disabling thinking for this draft step encourages final draft content in `message.content`.

Safety:
- no LLM calls
- no network calls
- no request sending
- no retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no final answer permission
- no direct answer permission
