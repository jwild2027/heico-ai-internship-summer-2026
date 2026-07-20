# TRACE-Net H30 Phase 4.4.1 — Shadow Planner Schema Repair v1

This focused patch fixes live Gemma planner proposals that understand the route but fail the strict JSON contract.

1. The raw proposal is validated unchanged.
2. Grounding, unsafe true flags, unapproved routes/tunnels, ATA/part conflicts, and exact/partial conflicts remain non-repairable.
3. Contract-shape failures may receive one schema-repair prompt containing the original proposal and exact validator failures.
4. The repaired proposal is passed through the same validator.
5. The deterministic route remains the effective route; planner execution and retrieval influence remain disabled.

The repair loop cannot add retrieved evidence to the seed, change answer permission, write databases, mutate source truth, or override grounding.
