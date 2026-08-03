# TRACE-Net H30 Phase 4.3 Part Intent and Source Resolution V1

## Purpose

Phase 4.3 makes part-number behavior explicit and inspectable. It separates exact,
prefix, contains, suffix, partial, and family queries; filters malformed or unrelated
candidate identifiers; performs bounded read-only attempts to resolve candidate and
visual leads to citation-ready source fields; and groups direct evidence by claim type.

## Intent contract

The router exposes these fields in `query_atoms` and in the evidence coverage metadata:

- `identifier_mode`
- `normalized_identifier`
- `family_identifier`
- `allow_family_expansion`
- `allow_partial_candidates`
- `explicit_partial_wording`

Explicit partial wording overrides exact-looking identifier syntax. An exact query only
accepts exact identifier equality. Family expansion is allowed only when the query says
family, series, or base number.

## Candidate rules

Candidates must be conservative alphanumeric/hyphen identifiers. Symbol-heavy OCR,
compound slash expressions, whitespace-corrupted tokens, and unrelated fallback
candidates are rejected. No OCR character repair is performed automatically.

Candidate discovery remains guidance only and never grants answer permission.

## Source resolution

The overlay performs bounded source-resolution requests through existing read-only
upstreams:

- one exact source-resolution request for an unresolved exact identifier;
- up to two candidate source-resolution requests for partial or family discovery.

Resolution records report whether a lead matched direct citation-ready evidence. They do
not promote guidance to source truth by themselves.

## Claim-specific evidence

Direct evidence is grouped into independent buckets such as:

- part identity
- nomenclature
- table item
- figure callout
- assembly relationship
- procedure step
- warning or caution
- authority

Evidence for one bucket does not automatically support another bucket.

## Safety contract

- Read-only during request handling.
- No source-truth mutation.
- No automatic PostgreSQL writes.
- No automatic Qdrant writes.
- No automatic OpenSearch writes.
- `answer_permission=false`.
- `final_answer_allowed=false`.
- `can_answer_directly=false`.
- `can_prove_claims=false`.
- Candidate discovery remains discovery-only.
- Authority-sensitive claims require explicit authority evidence.
- Port 8017 and port 8130 remain untouched.

## Runtime compatibility

The overlay is installed after retrieval completion, Engram critic/repair, user-facing
rendering, and the navigation latency fast path. Existing route names and tunnels remain
available; Phase 4.3 adds bounded source-resolution tunnel labels and metadata.

## Semantic benchmark

The patch includes `run_trace_net_h30_phase4_3_semantic_benchmark_v1.py`.
It supports a five-query focused gate and the existing 180-question bank. The evaluator
checks clue satisfaction, candidate validity, OCR-noise rejection, duplicate follow-ups,
citation alignment, requested claim buckets, safety flags, and fail-closed authority
behavior. It exports `records.jsonl`, `summary.json`, and `answers.txt` for semantic review.
