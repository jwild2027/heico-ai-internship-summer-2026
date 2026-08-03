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

## Default state

Enabled by default in the deployment launcher
(`scripts/launch_trace_net_cognitive_openwebui_v1.sh`) alongside
`TRACE_NET_H30_TYPED_EVIDENCE_ENABLED` (required — the mode classifier reads the
typed evidence envelope) and `TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED` (the
final deterministic validator). The Python module still defaults to disabled
when the env var is unset, so unit tests keep legacy behavior; the launcher opts
in with `TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED=1`. With this layer
on, a non-`confirmed_direct` question is rendered deterministically and reports
`gemma_status=SKIPPED_BY_TYPED_EVIDENCE_MODE` — the design target of zero or one
Gemma call per question, never two.

Rollback:

```text
TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED=0
```
