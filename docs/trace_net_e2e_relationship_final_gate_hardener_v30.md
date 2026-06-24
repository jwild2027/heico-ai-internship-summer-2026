# TRACE-Net E2E Relationship Final Gate Hardener v30

This phase validates and repairs relationship/synthesis answer drafts before they can become WebUI-ready final answers.

## Contract

- Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only.
- Relationship/synthesis answers may use guidance for navigation, but not as proof authority.
- Direct source-truth evidence is required for factual relationship claims.
- The gate catches claims such as “the Leiden community proves...”, “the V2 summary confirms...”, or “the nomenclature means...” when those are not backed by direct source-truth evidence.
- This stage does not call an LLM, scan raw 5TB source data, rebuild the graph, rerun OCR, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Inputs

- `trace_net_e2e_relationship_router_hardening_v29_1.json`

## Outputs

- `trace_net_e2e_relationship_final_gate_hardener_v30.json`
- `trace_net_e2e_relationship_final_gate_hardener_records_v30.jsonl`
- `trace_net_e2e_relationship_final_gate_hardener_v30.md`
