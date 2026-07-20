# TRACE-Net H30 Phase 4.3.1 — Exact Identifier and Planner Readiness v1

## Purpose

Phase 4.3.1 fixes the concentrated failures discovered by the 180-question Phase 4.3 semantic run while avoiding a list of hardcoded questions or identifiers.

The patch adds reusable reasoning patterns for:

- compact alphanumeric identifiers such as `VS4956` and `E075221`;
- valid identifiers with one-character segments such as `1002-F`;
- exact versus partial wording;
- ATA, page, figure, table, and document-reference separation;
- final exact-entity filtering after CRAG or source-resolution calls;
- broad manual/source overview intent;
- route-aware semantic benchmark evaluation.

## Engram and LLM planner direction

The patch also adds a proposal-only planner contract. It creates a grounded planner seed from the user query, deterministic query atoms, current route, and available Engram policy. A future Gemma planner may propose:

- entity type;
- identifier mode;
- requested claim types;
- suggested allow-listed routes;
- suggested allow-listed retrieval tunnels;
- uncertainties or clarification needs.

In Phase 4.3.1 the planner cannot execute. Its proposal validator rejects:

- identifiers not literally grounded in the user query;
- unknown fields;
- non-allow-listed routes or tunnels;
- any true answer-permission or source-mutation flag.

This provides the architecture needed for Phase 4.4 without allowing the LLM to select evidence, bypass source gates, or authorize engineering claims.

## Runtime flow

```text
User query
→ deterministic atoms and Phase 4.3.1 contextual identifier inference
→ Engram-backed planner seed (proposal only)
→ validated deterministic route
→ bounded retrieval
→ Self-RAG critic
→ CRAG repair when required
→ final exact-identifier filter
→ claim/source-resolution metadata refresh
→ Engineer Answer Contract
```

## Safety contract

The patch remains read-only:

- `answer_permission=false`
- `final_answer_allowed=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`
- no PostgreSQL writes
- no Qdrant writes
- no OpenSearch writes
- no OCR auto-correction
- no LLM planner execution

## Benchmark changes

The focused Phase 4.3 benchmark expands from 5 to 11 questions. It now includes representative compact identifiers, one-character identifier segments, ATA/document false-positive guards, and a general manual-overview query.

The full benchmark now maps the legacy question bank expectations to acceptable H30 cognitive routes. A broad manual-overview question routed to `clarification_no_evidence` therefore fails instead of receiving a false PASS.

## Phase 4.4 recommendation

Phase 4.4 should enable one bounded Gemma planning call only when deterministic confidence is low or clues conflict. TRACE-Net should validate the JSON proposal, execute only allow-listed tunnels, and preserve all existing source, authority, Self-RAG, CRAG, and answer boundaries.
