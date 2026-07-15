# TRACE-Net Engram Non-Redundancy Plan

## Phase 1 — policy compiler foundation — COMPLETE

- Select Engram before retrieval.
- Compile allowlisted retrieval, critic, repair, and presentation policy.
- Create fresh request-local working memory.
- Let retrieval completion consume ranking and presentation policy.

Gate passed: policy cannot execute arbitrary actions and the focused runtime
suite passed.

## Phase 2 — clean the memory taxonomy — COMPLETE

- Move static `working_memory` rules into persistent behavior layers.
- Keep working memory request-local only.
- Preserve readable core IDs and legacy aliases.
- Preserve allowed and forbidden behavior fields.
- Reject persisted static working-memory atoms.

Gate passed: static working-memory count is 0; all 21 persisted atoms have
readable IDs and populated behavior fields.

## Phase 3 — canonical rule registry — CURRENT PATCH

- Store each reusable lesson once.
- Replace copied rule text and policy effects with `inherits` references.
- Resolve multi-rule inheritance before policy compilation.
- Remove duplicate rule references across selected atoms.
- Fail closed when an inherited rule cannot be resolved.
- Detect duplicate canonical IDs and duplicate normalized meanings.

Gate: all references resolve, local copied rule/policy count is 0 in the H30
runtime packs, and the navigation policy remains unchanged.

## Phase 4 — policy-aware Self-RAG and CRAG

- Run critic checks selected by `critic_policy`.
- Record which checks passed or failed.
- Map allowlisted repair hints to existing bounded repair functions.
- Never let memory create free-form searches or exceed repair budgets.

Gate: every repair is allowlisted, inspectable, bounded, and read-only.

## Phase 5 — policy-aware route execution

- Move optional tunnel order and ranking preferences out of renderer code.
- Keep only absolute safety and adapter allowlists in deterministic code.
- Pass validated policy IDs to executors, not raw memory prose.
- Add safe fallback behavior when memory is missing or invalid.

Gate: all 19 routes pass both with and without Engram.

## Phase 6 — feedback and episodic learning

- Convert reviewed feedback and regression failures into episodic candidates.
- Link each episode to root cause, repair, and regression test.
- Merge repeated episodes under one canonical lesson.
- Require review and versioning before activation.

Gate: no automatic source-fact learning and no unreviewed active memory.

## Phase 7 — full regression and consolidation

- Run the full 19-route live matrix and the 200-question H30 bank.
- Compare policy, retrieval order, critic checks, repairs, and answer shape.
- Remove compatibility code only after equivalent behavior is proven.
- Publish one canonical runtime map for the final Engram path.

Gate: no internal IDs, no duplicate rules, and no unexplained hard-coded
presentation strategy.
