# TRACE-Net H30 Phase 4 — Typed Evidence Envelope

Phase 4 adds a canonical typed view over the existing evidence envelope.

## Why it exists

The current envelope already separates direct, candidate, visual, semantic,
authority, contradiction, and resolution material, but consumers still infer
many rules from bucket names and inconsistent row fields. Phase 4 makes those
rules explicit and machine-checkable.

Every typed record declares:

- its original legacy bucket and index;
- evidence class and modality;
- authority class;
- proof and resolution status;
- supported claim types;
- source-trace readiness;
- whether it is guidance-only;
- whether it is conflicted;
- whether it may support a final claim.

## Safety boundary

Only direct evidence with a usable source trace and direct field authority may
set `claim_support_allowed=true`.

Candidate, visual, semantic, graph, summary, source-resolution, and conflict
records always remain non-proof.

The legacy evidence lists remain unchanged. Retrieval, ranking, Self-RAG,
CRAG, answer writing, and source-truth stores are untouched.

## Rollback

Set:

```text
TRACE_NET_H30_TYPED_EVIDENCE_ENABLED=0
```

No database or artifact rollback is required.
