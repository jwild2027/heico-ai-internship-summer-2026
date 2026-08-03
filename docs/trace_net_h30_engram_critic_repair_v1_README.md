# TRACE-Net Engram Policy-Aware Self-RAG and CRAG — Phase 4

## Purpose

Phase 4 makes the compiled Engram `critic_policy` and `repair_policy` active.

The deterministic router critic remains the permanent safety floor. Engram adds
only selected checks and selected repairs.

## Flow

```text
base deterministic critic
→ selected Engram checks
→ route-applicability filter
→ recorded PASS/WARN/FAIL per check
→ selected repair hints intersect failed checks
→ at most one bounded repair per iteration
→ local retrieval completion refresh
→ critic runs again
```

## Route filtering

A selected memory may inherit rules useful to another route. Those checks are
not silently executed.

Example:

- navigation may inherit an aggregation lesson due a shared exact-identifier
  trigger;
- `aggregation_coverage_required` is recorded as skipped because the current
  route is navigation;
- navigation checks still run.

## Repair boundary

Repairs are fixed functions, not free-form actions:

- retry a registered specialized tunnel;
- retry explicit authority fields;
- rerank exact entities;
- collapse repeated page rows;
- sanitize internal IDs;
- retry stored OCR records;
- expand indexed aggregation coverage;
- rebuild claim buckets;
- retry direct source resolution.

One repair runs per loop iteration, and the existing route repair budget remains
the hard maximum.

## Safety

- no arbitrary queries from memory;
- no database writes;
- no source-truth mutation;
- no answer permission;
- no guidance-to-proof promotion;
- all check and repair execution is returned in the evidence envelope.
