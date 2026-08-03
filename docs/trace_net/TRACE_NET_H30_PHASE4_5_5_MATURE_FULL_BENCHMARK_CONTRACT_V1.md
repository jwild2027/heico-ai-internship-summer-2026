# TRACE-Net H30 Phase 4.5.5 — Mature Full-Benchmark Contract

## Purpose

Phase 4.5.5 fixes the contract mismatch discovered when the legacy 180-question
bank was sent through the current H30 mature cognitive OpenWebUI stack.

## Changes

- The full benchmark derives the current expected route and tunnel plan from the
  H30 deterministic router while preserving the legacy bank fields for audit.
- Current multi-tunnel fields are validated from `route_plan.retrieval_tunnels`
  and `evidence_envelope.retrieval_tunnels_used`.
- Candidate-only answers correctly require the deterministic writer path and
  `SKIPPED_NO_DIRECT_EVIDENCE`.
- Direct citation-ready answers require the validated Gemma writer path.
- Guided part discovery deterministically generates at least four bounded,
  relevant clarification questions.
- The final cognitive writer exposes those questions once in the user answer.
- Revision metadata such as `REV.4` is excluded from part-candidate noise checks.
- Existing safety boundaries and legacy canary compatibility remain intact.

## Safety

The patch does not grant answer permission, alter source truth, write databases,
or allow the planner/model to own retrieval tunnel execution.
