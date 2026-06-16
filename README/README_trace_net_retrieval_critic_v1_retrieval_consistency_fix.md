# TRACE-Net Retrieval Critic v1 Retrieval-Consistency Fix

This patch tightens the Self-RAG-style retrieval critic so it does not blindly trust a dynamic final-gate approval when the approval does not align with the retrieval pattern for the query.

## What changed

The critic now audits dynamic final-gate approvals when:

- an exact identifier query has no exact-hit groups,
- an exact identifier or revision query has no answer-support groups,
- all retrieval groups are retrieval-only,
- a topic query has neither semantic nor exact support,
- a dynamic approval uses an unrecognized answer status.

Full prebuilt final-gate artifact answers are exempt from retrieval-pattern audits because they already passed the earlier full TRACE-Net final-gate artifact pipeline.

## Safety behavior

The critic remains advisory-only:

- it cannot answer directly,
- it cannot prove claims,
- it cannot mutate source truth,
- it cannot treat feedback, communities, or categories as proof.

## Expected impact

For the known final-gate artifact query, the critic may still report:

```text
final_gate_already_authorized
```

For dynamic approvals that are structurally questionable, the critic should now report:

```text
dynamic_final_gate_needs_audit
```

with reason codes such as:

```text
dynamic_final_gate_exact_query_missing_exact_hits
dynamic_final_gate_missing_answer_support_groups_for_exact_query
dynamic_final_gate_retrieval_pattern_only_retrieval_groups
```
