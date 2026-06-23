# TRACE-Net E2E Live Orchestrator Endpoint v25

v25 is the first endpoint stage that can answer new Open WebUI questions by running a compact live TRACE-Net pipeline at request time.

Flow:

1. Parse user query into a query plan.
2. Search prebuilt source-truth exact-search evidence.
3. Attach bounded Leiden/graph guidance and v2 page-summary guidance.
4. Build a compact prompt.
5. Optionally call a local LLM through Ollama.
6. Treat the LLM output as a draft only.
7. Rebuild the final answer from direct source-truth evidence and final-gate rules.
8. Return a WebUI-ready OpenAI-compatible response.

Safety contract:

- Source-truth evidence is the only proof authority.
- Graph/Leiden and v2 summaries are guidance only.
- Nearby OCR/table context is not direct proof.
- The endpoint reads prebuilt artifacts and does not scan raw 5TB data.
- It does not rebuild the graph, rerun OCR, mutate source truth, or write to services.
- If no direct evidence is found, the endpoint returns an audit-only no-claim response.
