# TRACE-Net Engram Non-Redundancy Plan

## Phase 1 — policy compiler foundation

- Select Engram before retrieval.
- Deduplicate selected memories by canonical rule ID.
- Compile allowlisted retrieval, critic, repair, and presentation policy.
- Create fresh request-local working memory.
- Let retrieval completion consume ranking and presentation policy.

Gate: all existing route tests pass; policy cannot execute arbitrary actions.

## Phase 2 — clean the memory taxonomy

- Move static `working_memory` rules into semantic or procedural memory.
- Keep working memory request-local only.
- Rename hashed H17 atom IDs and titles with readable canonical names.
- Populate meaningful allowed and forbidden behavior fields.
- Keep aliases for old IDs so history remains traceable.

Gate: every static atom has the correct layer and a readable canonical ID.

## Phase 3 — canonical rule registry

- Create one canonical record for each shared lesson.
- Replace copied rule text with `canonical_rule_id` references.
- Let route atoms inherit shared rules instead of repeating them.
- Add duplicate detection by canonical ID and normalized meaning.

Gate: no duplicate active canonical rules and all references resolve.

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
