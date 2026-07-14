# TRACE-Net H30 Benchmark Failure Repair v1

## Purpose

Repair every failure class observed in the completed 200-question H30 baseline without weakening route, source-truth, authority, or read-only safety gates.

Baseline:

- completed: 200/200
- route coverage: 19/19
- route mismatches: 0
- HTTP failures: 0
- structural safety failures: 0
- overall pass: 112/200
- semantic pass: 142/200
- raw benchmark Gemma pass: 127/200

Observed failure classes addressed:

- missing fail-closed boundary without direct evidence
- requested field not addressed
- authority-sensitive wording without explicit authority
- missing item, page, exact identifier, ATA, figure, nomenclature, prefix, contains, or suffix clue
- unsupported Gemma page or identifier
- empty Gemma answer

## Changes

### Canonical answer boundary module

`scripts/trace_net_h30_answer_boundary_v1.py` adds deterministic route, clue, proof, conflict, and authority boundaries. It never promotes guidance into proof.

For technical routes without direct evidence, the user-visible answer now explicitly states that no direct citation-ready source evidence was found and that candidate, visual, semantic, graph, summary, OCR, and table-derived results remain guidance only.

For authority-sensitive questions without explicit authority evidence, the answer explicitly states that no authority was found and no approval, fit, effectivity, interchangeability, eligibility, applicability, or installation claim is confirmed.

### Cognitive router

`serve_trace_net_cognitive_router_v1.py` applies the boundary module after deterministic rendering. This covers early-return routes such as ATA and authority as well as the shared renderer.

### Benchmark runner

`run_trace_net_h30_server_benchmark_200_v1.py`:

- uses schema version 5 and a new runtime directory;
- applies the same deterministic boundary contract before the mandatory Gemma render;
- records raw Gemma validation separately;
- uses the validated deterministic draft when raw Gemma output is empty, unsupported, unbounded, or authority-unsafe;
- preserves raw output, raw failures, fallback reasons, and final render mode in every record;
- reports raw Gemma pass count and bounded-fallback count separately from final validated pass count.

This is not a hidden raw-model pass. A rejected raw model answer remains visible as `benchmark_gemma_raw_pass=false`, while the final full-stack answer may pass after the explicit post-answer-validation fallback.

### Safety contract

Unchanged:

- read-only;
- no Postgres writes;
- no Qdrant writes;
- no OpenSearch writes;
- no source-truth mutation;
- no final-answer permission flags;
- guidance is not proof;
- production Gemma still requires direct citation-ready evidence.

## New runtime

`/data/trace_net_runs/cognitive_benchmark_200_failure_repair_v1`
