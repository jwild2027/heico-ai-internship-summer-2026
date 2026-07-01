# TRACE-Net Engineering Context Self-RAG Check v1

Scores engineering context packs before Gemma drafting.

It checks:
- source-truth evidence strength
- candidate-only evidence
- missing evidence notes
- route coverage
- forbidden-claim risk
- CRAG retry need
- draft readiness

It does not call an LLM, execute retrieval, answer the user, write DBs, mutate source truth, or grant final answer permission.
