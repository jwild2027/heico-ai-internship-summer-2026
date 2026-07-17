# TRACE-Net H30 Engineer Answer Contract v1

## Phase

Phase 4.2.1

## Purpose

Add a deterministic, post-validation answer contract for engineer-facing TRACE-Net responses.

## Current-state base

- Branch: `srv`
- Commit: `3f12f8883976654a8a5d775aee1abeafad350a08`
- Requires Phase 4.2.0 cold-start/validated streaming.
- Requires Phase 4.2.0.1 exact-part navigation latency fastpath.

## Behavior

- Preserves strict alphanumeric identifier prefixes.
- Adds no unrelated fallback candidates.
- Removes only obvious symbol-only OCR garbage lines.
- Deduplicates identical answer/follow-up lines.
- Preserves citations, routes, and selected tunnels.
- Replaces misleading `confirmed visual guidance` wording.
- Separates direct source proof, guidance-only results, contradictions, and insufficient evidence.
- Keeps explicit authority requirements fail-closed.

## Safety contract

- `answer_permission=false`
- `final_answer_allowed=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`
- No PostgreSQL, Qdrant, or OpenSearch writes.
- No source-truth mutation.
- Candidate discovery remains discovery-only.
- Raw unvalidated Gemma output remains blocked.
- Port 8130 remains untouched.
