# TRACE-Net H14B Engineering LLM Scaffold + Negation Gate Fix v1

This patch updates `tiff/trace_net_engineering_llm_answer_smoke_v1.py` after the H14 rerun exposed two issues:

1. Pipeline/debug questions such as “Why was nomenclature missing from the visual route evidence?” and “What changed after the raw OCR nomenclature extractor was added?” could return blank/BLOCKED answers because the prompt did not give the LLM enough structured pipeline context.
2. The unsupported-claim detector could count safe negated statements such as “not an approved replacement” as unsupported claims because it saw the approval phrase without enough sentence-level negation handling.

## Changes

- Adds intent-specific LLM prompt instructions directly in the H13 module.
- Adds a `STRUCTURED_TRACE_NET_SCAFFOLD` section derived from the TRACE-Net runner answer and proof-context citation families.
- Adds pipeline scaffolding for visual/OCR nomenclature explanation questions.
- Strengthens negation-aware unsupported-claim detection at sentence level.
- Keeps the core safety contract: no DB writes, no source-truth mutation, no answer permission, no unsupported positive approval claims.

## Safety contract

- No writes to Postgres/Qdrant/OpenSearch.
- No source-truth mutation.
- No answer permission granted.
- Local JSON/CSV/prompt/answer artifacts only.
