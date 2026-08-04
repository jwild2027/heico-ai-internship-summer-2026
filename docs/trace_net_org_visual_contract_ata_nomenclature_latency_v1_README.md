# TRACE-Net Org Visual Contract + ATA/Nomenclature Latency Patch v1

## Scope

This focused patch targets two findings from the completed public 8131 benchmark:

1. Technical fail-closed responses could contain only `## Answer`, causing the public contract to fail because `## Evidence` was absent. This affected visual no-evidence requests and the same structural condition on contradiction, OCR, aggregation, and multi-question routes.
2. ATA and nomenclature discovery repeatedly landed on a roughly 45-second retrieval plateau.

## Changes

- Structures deterministic technical fallback output as `## Answer`, `## Evidence`, and `## Limits`.
- Uses route-specific visual wording when no visual record is recovered.
- Does not fabricate citations or promote visual/candidate/semantic guidance to proof.
- Reorders ATA and nomenclature retrieval to run guided candidate discovery first.
- Skips the slower source-truth tunnel when matching candidates already exist.
- Retains one bounded source-truth fallback when guided discovery returns no candidates.
- Adds `elapsed_ms` to each router upstream tunnel record.
- Adds `TRACE_NET_H30_DISCOVERY_TUNNEL_TIMEOUT_SECONDS` with a default of 12 seconds, clamped to 1–30 seconds.

## Explicit non-changes

- No source-truth mutation.
- No PostgreSQL, Qdrant, or OpenSearch writes.
- No route-selection changes.
- No authority-policy weakening.
- No Gemma writer-policy change. The always-Gemma final-writer architecture is a separate patch after these retrieval/contract fixes are verified.
- No changes to ports 8116, 8117, or 8131.

## Files

Modified by `APPLY_ME.py`:

- `src/trace_net/writing/trace_net_h30_evidence_aware_answer_modes_v1.py`
- `scripts/operations/router/serve_trace_net_cognitive_router_v1.py`

Added:

- `tests/unit/test_trace_net_h30_fail_closed_public_contract_v1.py`
- `tests/unit/test_trace_net_h30_ata_nomenclature_guided_first_v1.py`
- `docs/trace_net_org_visual_contract_ata_nomenclature_latency_v1_README.md`

## Expected focused result

The focused tests should report PASS. Runtime validation should show:

- visual/no-evidence technical answers include Answer, Evidence, and Limits;
- ATA/nomenclature retrieval executes guided first;
- a matching guided candidate prevents the slow source-truth call;
- an empty guided result permits one source fallback bounded by the discovery timeout;
- 8118 and 8128 remain healthy;
- 8131 remains running and is not restarted.
