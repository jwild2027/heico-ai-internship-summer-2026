# TRACE-Net mandatory constrained Gemma for validated technical routes v1

## Purpose

TRACE-Net remains responsible for route selection, retrieval, evidence typing,
source authority, deterministic fail-closed drafting, and final validation.
Gemma receives the already-validated deterministic packet and gets exactly one
bounded opportunity to author the `Answer` section for every validated technical
route.

This includes direct-evidence, candidate, semantic, visual, conflict,
authority-missing, OCR, aggregation, comparison, navigation, and no-evidence
technical responses. Empty citation registries and negative/no-evidence drafts
are valid writer inputs in mandatory mode.

## Safety contract

- The model does not retrieve, select, rank, or promote evidence.
- The model cannot modify deterministic `Evidence` or `Limits` sections.
- Added or changed part numbers, ATA codes, page IDs, figures, or citations are
  rejected.
- Unsupported authority, fit, effectivity, eligibility, safety, or
  interchangeability claims remain blocked.
- A malformed, timed-out, or rejected model response falls back to the already
  validated deterministic answer.
- At most one Gemma call is attempted per request.
- No source-truth, PostgreSQL, Qdrant, or OpenSearch write is performed.

## Runtime switch

```text
TRACE_NET_H30_CONSTRAINED_WRITER_MANDATORY_TECHNICAL_ROUTES=1
```

The production launchers enable this switch by default. Set it to `0` to return
to the prior route-canary eligibility policy.

## Acceptance gate

The focused 27-question benchmark should report:

```text
completed=27/27
http_200_count=27/27
contract_pass_count=27/27
route_mismatch_count=0
timeout_cluster_count=0
gemma_called_count=27
```

A Gemma output may still be rejected by safety validation; that is an expected
safe fallback, but the single call attempt must be visible in
`constrained_gemma_writer.call_count=1` and
`mandatory_call_satisfied=true`.
