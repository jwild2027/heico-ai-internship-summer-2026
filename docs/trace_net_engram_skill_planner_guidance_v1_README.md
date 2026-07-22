# TRACE-Net H30 Phase 3

Phase 3 permits only the reviewed `partial_identifier_discovery` skill to
influence the LLM planner seed.

It applies only to a grounded prefix, contains, suffix, or family clue whose
deterministic route is `guided_part_discovery`.

The skill may provide the required route, identifier mode, grounded fragment,
required `part_identity` claim, forbidden route changes, and preferred
read-only tunnels.

The deterministic executor still owns actual tunnel selection. A proposal
that changes the fragment, changes partial mode to exact, or changes to an
inapplicable route fails closed to the deterministic plan.

The answer writer remains unchanged and the Phase 2 answer shadow remains
shadow-only.

Disable instantly with:

```text
TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED=0
```
