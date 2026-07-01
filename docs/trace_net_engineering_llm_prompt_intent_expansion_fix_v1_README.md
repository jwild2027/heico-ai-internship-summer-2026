# TRACE-Net H14 Engineering LLM Prompt Intent Expansion Fix v1

This patch hardens `trace_net_engineering_llm_answer_smoke_v1` prompt construction so the local LLM gives more useful conservative answers instead of overusing generic `not proven` responses.

It adds intent-specific prompt rules for:

- interchangeability and replacement approval limits
- installation safety, fit, and effectivity limits
- unknown part / unknown figure handling
- troubleshooting and pipeline-recovery questions
- evidence-support, source-page, route-explanation, and visual-vs-OCR questions
- comparisons and nomenclature summaries

Safety contract:

- No writes to Postgres, Qdrant, or OpenSearch.
- No source-truth mutation.
- No answer permission granted.
- The patch only changes local Python prompt text used for LLM smoke testing.

After applying, rerun only the not-proven / partial categories first before the full 30-question smoke.
