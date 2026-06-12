# TRACE-Net Retrieval Critic v1 Dynamic Gate Tightening

This patch tightens Retrieval Critic v1 so it does not blindly trust a dynamic final-gate result only because `final_answer_allowed` is true.

The critic now requires a query-specific final-gate result to have:

- final answer allowed
- at least one final claim or final answer text
- zero uncited final claims
- zero retrieval-only final claims
- zero source-truth mutation risk
- zero feedback/community/category-as-proof counters
- zero local path/raw byte leak counters

If a dynamic final-gate record is marked allowed but lacks safe claim/output evidence, the critic emits:

```text
critic_status = dynamic_final_gate_needs_audit
recommended_next_action = audit_dynamic_final_gate_before_returning_answer
```

This keeps Retrieval Critic v1 advisory-only and prevents a Self-RAG-style critic from over-trusting stale or incomplete gate metadata.
