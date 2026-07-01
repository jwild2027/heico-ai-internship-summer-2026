# TRACE-Net Engineering WebUI Answer Server v1.2

v1.2 quality patch:
- retries Gemma4 once when first LLM response is empty
- cleans raw fishnet/router classifier text before prompt and fallback output
- only uses gated lookup when requested seed part matches the gated draft
- appends visible source notes to answers
- preserves lookup, random page summary, and fallback artifact search

Safety: no DB writes, no source-truth mutation, no final answer permission.
