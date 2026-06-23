# TRACE-Net E2E Dynamic Context Pack v8

`trace_net_e2e_dynamic_context_pack_v8` is the first context-engineering layer after dynamic hybrid retrieval and tunnel ranking.

It consumes the v6 dynamic tunnel ranker and builds LLM-readable context packs with three explicit sections:

1. **Evidence box** — source-truth records that may be cited.
2. **Guidance box** — vector/page-profile, summary, graph, route, and table-route hints that help navigation but are not proof.
3. **Rules box** — answer permissions, citation policy, uncertainty behavior, and non-mutation contract.

The module does not call an LLM. It also does not rerun OCR, page classification, embeddings, page summaries, graph construction, table extraction, source ingest, or service writes.

This prepares the next phase: Self-RAG context critique.
