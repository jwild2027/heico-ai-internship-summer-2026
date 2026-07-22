# TRACE-Net H30 Final Engram Rollout — Phases 6–10

This consolidated patch closes the remaining middle-ground roadmap.

## Phase 6 — Information-gain follow-ups

Follow-up questions are selected from missing query atoms and the active Engram
skill. Known clues are not asked again. Candidate ambiguity prioritizes the
questions most likely to separate remaining candidates.

## Phase 7 — Final Self-RAG critic

The critic checks typed-evidence validation, answer-mode validation, direct
support for confirmed answers, non-promotion of guidance, required uncertainty
language, follow-up relevance, uniqueness, and safety boundaries.

## Phase 8 — Bounded CRAG-compatible repair

At most one deterministic final-response repair is allowed. It may re-render a
non-direct answer from the existing typed answer mode and replace weak
follow-ups. It cannot rerun retrieval, execute tools, select new evidence, or
write to source truth.

## Phase 9 — Benchmark redesign

The benchmark supports:

- fast local contract mode;
- optional live endpoint mode;
- durable JSONL writes;
- resume;
- quick and full banks;
- interruption summaries;
- explicit safety and phase metadata.

It does not invoke the five critical live route tests.

## Phase 10 — Broad rollout

Response behavior covers all five Engram skill cards:

1. partial identifier discovery;
2. exact identifier lookup;
3. nomenclature/function discovery;
4. ATA plus description discovery;
5. manufacturer plus description discovery.

Engram remains behavior guidance only. Typed evidence remains the proof
boundary.

## Expensive route-smoke policy

The launcher now defaults to:

```text
TRACE_NET_RUN_CRITICAL_LIVE_ROUTE_SMOKE=0
```

Set it to `1` only for router, planner, retrieval, Self-RAG execution, CRAG
execution, full benchmark, or release gates.
