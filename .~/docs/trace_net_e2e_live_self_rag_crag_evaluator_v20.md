# TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20

Builds Self-RAG and CRAG evaluation records from v19 executed-plan context packs.

The module keeps source-truth evidence separate from graph/Leiden and v2 summary guidance. It treats capped or high-degree graph/entity results as usable only when the final answer preserves aggregation/cap disclosure and offers drill-down behavior. It does not call an LLM, scan raw corpus data, rebuild graph data, mutate source truth, or write to services.

Primary output:

- `trace_net_e2e_live_self_rag_crag_evaluator_v20.json`
- `trace_net_e2e_live_self_rag_crag_evaluator_records_v20.jsonl`
- `trace_net_e2e_live_self_rag_crag_evaluator_crag_plans_v20.jsonl`
- `trace_net_e2e_live_self_rag_crag_evaluator_v20.md`

Authority contract:

- Source-truth evidence is required for final factual claims.
- Graph/Leiden guidance is navigation only.
- v2 summaries are guidance only.
- Capped/high-degree results must disclose total vs returned evidence.
- Query-time processing must not scan raw 5TB source data.
