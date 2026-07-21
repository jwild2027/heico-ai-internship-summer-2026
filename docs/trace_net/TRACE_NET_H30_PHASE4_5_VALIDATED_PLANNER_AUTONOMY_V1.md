# TRACE-Net H30 Phase 4.5 — Validated Planner Autonomy v1

## Purpose

This package implements rollout phases 2 through 5 of the Gemma planning architecture while keeping TRACE-Net as the validator, read-only executor, evidence critic, and safety boundary.

The planner remains a proposal engine. It never receives direct tool handles, never selects evidence, never grants answer permission, and never writes PostgreSQL, Qdrant, OpenSearch, or source truth.

## Rollout modes

### Phase 2 — `validate_only`

Gemma proposes a structured plan. TRACE-Net validates, canonicalizes only benign schema drift, compares it to the deterministic router, and records the result. Retrieval remains entirely deterministic.

### Phase 3 — `narrow`

Accepted and grounded plans may select only:

- `exact_identifier_lookup`
- `exact_table_ipl_lookup`
- `document_page_navigation`
- `semantic_discovery`

TRACE-Net checks route-specific prerequisites and uses executor-owned fixed tunnel plans.

### Phase 4 — `broad`

Adds read-only planning for:

- guided part discovery
- ATA discovery
- nomenclature/function search
- visual and figure lookup
- procedure and warning retrieval
- graph relationships
- cross-source comparison
- OCR recovery

Authority, contradiction, high-degree aggregation, multi-question orchestration, and clarification remain excluded.

### Phase 5 — `mature`

Accepted plans may lead route selection across the complete read-only technical route family. High-consequence routes still require explicit query atoms. Authority questions remain evidence-gated, Self-RAG and CRAG remain active, and final answer boundaries remain deterministic.

## Two switches are required

Merely setting a rollout mode does not enable planner-led retrieval. Both are required:

```bash
export TRACE_NET_H30_PLANNER_ROLLOUT_MODE=narrow
export TRACE_NET_H30_PLANNER_EXECUTION_ENABLED=1
```

The default is:

```text
rollout_mode=validate_only
execution_enabled=false
```

## Deterministic safety floor

Every planner-led route must satisfy all of the following:

1. The planner call completed successfully.
2. The strict proposal validator accepted the plan, or the deterministic canonical bridge produced a plan that the same validator accepted.
3. No identifier was invented.
4. All safety booleans are explicitly false.
5. Every route and tunnel is allow-listed.
6. The selected route is enabled for the active rollout phase.
7. Route-specific query prerequisites are present.
8. Planner latency is inside the configured budget.
9. Planner execution is explicitly enabled.

Any failure uses the original deterministic plan.

## Canonical contract bridge

The bridge handles benign output drift such as:

- `part` → `part_number`
- `exact_identifier` → `part_identity`
- omitted false safety fields
- an omitted identifier when exactly one query-grounded deterministic identifier exists

It never repairs:

- invented identifiers
- true safety or permission flags
- unapproved routes or tunnels
- write/admin requests
- source-truth mutation requests

The bridged proposal is always sent through the unchanged strict validator.

## Executor-owned tunnels

Gemma may suggest tunnels for comparison and audit. It never controls the actual tunnel list. TRACE-Net maps the selected route to a fixed read-only tunnel plan.

## Circuit breaker

Repeated planner transport failures open a bounded circuit breaker. While open, requests immediately use deterministic routing rather than repeatedly waiting for a failing planner.

Environment controls:

```bash
export TRACE_NET_H30_PLANNER_MAX_LATENCY_MS=90000
export TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD=2
export TRACE_NET_H30_PLANNER_BREAKER_SECONDS=300
export TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED=1
```

For the server, also lower the shadow-planner HTTP timeout from the earlier 300-second experimental value:

```bash
export TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS=90
```

## New endpoint

`POST /api/trace-net/planner-decision`

This runs planner interpretation and validation but does not execute retrieval. It reports:

- deterministic route
- proposed routes
- route prerequisite results
- selected route
- whether the plan would be adopted
- deterministic fallback reasons
- canonical bridge use
- schema repair use
- safety contract

## Promotion method

Recommended deployment order:

1. `validate_only` benchmark
2. `narrow` planner-decision benchmark
3. narrow live smoke
4. narrow 180-question benchmark
5. `broad` planner-decision benchmark
6. broad live smoke and regression
7. `mature` planner-decision benchmark
8. mature live smoke
9. mature 180-question comparison against the 136/180 deterministic baseline

Do not promote solely because adoption is high. Promotion also requires zero writes, zero permission changes, correct exact-ID behavior, bounded latency, and no loss of Self-RAG/CRAG or answer-boundary behavior.
