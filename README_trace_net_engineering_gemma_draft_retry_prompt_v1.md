# TRACE-Net Engineering Gemma Draft Retry Prompt v1.1

Builds a stricter, shorter Gemma retry request for drafts blocked by the final gate.

v1.1 adds micro prompt mode for Gemma4 fragment failures:
- avoids JSON prompt blobs by default
- avoids Markdown heading symbols like `###`
- uses fewer evidence snippets by default
- requires complete sentences and a minimum draft length
- stays runner-compatible with `engineering_gemma_draft_runner_v1`

Default mode:
- `--prompt-style micro`
- `--max-source-truth-items 3`
- `--max-candidate-items 2`
- `--ollama-think false`

Safety:
- no LLM calls
- no network calls
- no retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no final answer permission
