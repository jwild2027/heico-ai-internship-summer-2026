# TRACE-Net H30 Phase 4.4 Shadow Planner v1

## Purpose

Phase 4.4 begins moving TRACE-Net from a mostly rule-driven interpreter toward a validated LLM-assisted planner. Gemma receives the user query, deterministic atoms, deterministic route, Engram policy, explicit route/tunnel allow-lists, and immutable safety rules. It returns a structured proposal.

The proposal is **shadow-only** in this phase. It is validated and recorded, but it does not change retrieval, evidence, rendering, answer permission, or any write path.

## Architecture

```text
User query
→ deterministic atom extraction
→ deterministic route and Engram policy
→ trusted shadow-planner seed
→ Gemma structured proposal
→ deterministic proposal validator
→ proposal trace and disagreement metrics
→ original deterministic retrieval route
→ Self-RAG / CRAG
→ final evidence filters
→ existing Gemma writer
```

The planner runs before retrieval. No retrieved text, OCR, table content, graph content, visual observation, candidate evidence, or direct evidence is placed in the planner seed. This prevents retrieved prompt injection from steering route planning.

## Planner may propose

- entity type
- exact, partial, prefix, contains, suffix, family, or descriptive intent
- requested claim types
- up to three allow-listed routes
- up to five allow-listed read-only tunnels
- uncertainties

## Planner may not

- execute retrieval
- select or promote evidence
- invent an identifier
- write PostgreSQL, Qdrant, or OpenSearch
- mutate source truth
- grant answer permission
- authorize approval, interchangeability, fit, or safety claims
- change the effective deterministic route

## Validation

The validator rejects proposals that:

- do not match the required JSON shape
- omit required false safety flags
- introduce an identifier not grounded in the query or deterministic candidate tokens
- confuse a bound ATA value with a part number
- use exact mode when the query explicitly says partial, contains, starts with, family, or only remember
- propose a route or tunnel outside the read-only allow-list
- exceed route, tunnel, claim, or uncertainty budgets

## Runtime trace

Each normal cognitive response adds:

- `shadow_planner`
- `planner_proposal`
- `planner_validation`
- `planner_route_applied=false`
- `planner_retrieval_influenced=false`

The `shadow_planner.comparison` object records deterministic/planner route and identifier-mode disagreement. The effective route remains deterministic.

## Planner-only endpoint

`POST /api/trace-net/shadow-plan`

This endpoint performs deterministic parsing, Engram selection, the Gemma proposal, and validation without running retrieval. It is used for low-cost shadow evaluation.

## Configuration

```text
TRACE_NET_H30_SHADOW_PLANNER_ENABLED=1
TRACE_NET_H30_SHADOW_PLANNER_BASE_URL=http://127.0.0.1:11434/v1
TRACE_NET_H30_SHADOW_PLANNER_API_KEY=ollama
TRACE_NET_H30_SHADOW_PLANNER_MODEL=gemma4:26b
TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS=300
```

The canary launcher enables shadow mode by default. Setting `TRACE_NET_H30_SHADOW_PLANNER_ENABLED=0` returns the existing deterministic behavior with a skipped planner trace.

## Safety contract

Persistent values:

```text
shadow_planner_execution_enabled=false
shadow_planner_route_applied=false
shadow_planner_retrieval_influenced=false
answer_permission=false
final_answer_allowed=false
can_answer_directly=false
can_prove_claims=false
source_truth_mutation_allowed=false
postgres_write_attempt=false
qdrant_write_attempt=false
opensearch_write_attempt=false
```

## Exit criteria for a later narrow-execution phase

Do not let planner proposals influence retrieval until shadow telemetry shows:

- stable schema/parse success
- high grounded-proposal acceptance
- improved route suitability on hidden semantic questions
- no identifier invention
- no unsafe flag attempts accepted
- no write-path activity
- acceptable latency
- no increase in candidate contamination or unsupported claims

Phase 4.4 v1 is therefore an observation and evaluation layer, not an execution-autonomy layer.
