# TRACE-Net H30 Phase 5 — Evidence-Aware Answer Modes

Phase 5 makes the final response shape depend on the Phase 4 typed evidence
envelope.

## Modes

- `confirmed_direct`: claim-supporting direct evidence exists; the existing
  validated Gemma writer remains available.
- `candidate_discovery`: candidate identifiers exist without direct proof.
- `visual_guidance`: visual leads exist without direct proof.
- `semantic_graph_summary_guidance`: semantic, graph, summary, or
  source-resolution guidance exists only.
- `conflict_limited`: unresolved conflicts exist without claim-supporting
  direct evidence.
- `authority_not_found`: an authority request lacks explicit authority proof.
- `no_evidence`: no typed record can support or safely guide the claim.
- general-chat and upstream-error modes remain passthrough.

Only `confirmed_direct` may use Gemma. All other technical modes are
deterministic. Routes, retrieval, evidence selection, Self-RAG, CRAG, source
truth, and databases remain unchanged.

Rollback:

```text
TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED=0
```
