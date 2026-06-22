# TRACE-Net E2E LLM Prompt Contract v11

`trace_net_e2e_llm_prompt_contract_v11` is Phase 4 of the latter-half TRACE-Net pipeline.

It consumes:

- dynamic context pack v8
- Self-RAG context critic v9
- CRAG retrieval corrector v10

It emits strict LLM-ready prompt packets, but it does **not** call an LLM.

## Contract

The prompt builder is non-mutating and uses prebuilt artifacts only. It does not rerun retrieval, OCR, page classification, embeddings, summaries, graph construction, table extraction, or source ingest.

## Prompt sections

Each prompt packet separates:

1. `SOURCE-TRUTH EVIDENCE` — only this section can support factual claims.
2. `GUIDANCE ONLY` — graph, summary, vector/page-profile, route, and table-route context. This is not proof.
3. `ANSWER RULES` — citation, uncertainty, and safety rules.
4. Self-RAG status — whether the context is safe and ready.
5. CRAG status — whether retry/review is needed before generation.

## Output files

- `trace_net_e2e_llm_prompt_contract_v11.json`
- `trace_net_e2e_llm_prompt_contract_records_v11.jsonl`
- `trace_net_e2e_llm_prompt_messages_v11.jsonl`
- `trace_net_e2e_llm_prompt_contract_v11.md`

## Next phase

Phase 5 should be `trace_net_e2e_reasoned_response_draft_v12`, which uses the v11 prompt contract to generate a grounded draft answer.
