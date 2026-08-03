# TRACE-Net H30 Phase 4.5.3 Planner-Aware Route Smoke v1

The cognitive route smoke originally required every live response to equal the
deterministic route. That contract became outdated once validated planner
execution was enabled.

This change permits a live route difference only when all of the following hold:

- rollout mode is narrow, broad, or mature;
- planner decision quality is PASS;
- planner plan was adopted and applied;
- retrieval was explicitly influenced;
- deterministic fallback was not used;
- the decision has no failures;
- selected route exactly equals the effective route;
- content is present; and
- source-truth mutation remains false.

Plan-only route checks remain deterministic. Unexplained reroutes still fail.
No retrieval, validation, evidence, database, answer-permission, or planner
execution logic is changed.
