# TRACE-Net Ask Hybrid Flag v1 In-Memory Hydration Fix

This patch fixes a Step 9 ask-hybrid edge case discovered after the hydration fix.

## Problem

`hydrate_hybrid_report()` loaded `report_path` from disk even when the current Step 7 return object already contained fresh `results` / `query_results`. If a previous hybrid runtime report still existed at that path, the ask wrapper could summarize stale groups instead of the current in-memory Step 7 groups.

In tests this surfaced as:

```text
assert report["summary"]["ranked_group_count"] == 1
E assert 8 == 1
```

## Fix

The ask wrapper now prefers current in-memory Step 7 results when present. It only hydrates from `report_path` when the Step 7 return object is compact and does not already include `results` or `query_results`.

This preserves the intended Step 9 behavior:

```text
fresh Step 7 results -> ask retrieval preview
compact Step 7 return -> hydrate report_path/groups_path
stale disk artifacts -> ignored when current results exist
```

## Safety contract

This patch does not change TRACE-Net retrieval safety rules:

- hybrid ask mode is still simulation-only;
- no final answer is composed;
- vector hits cannot answer directly;
- vector hits cannot prove claims;
- source truth is not mutated;
- future answer use still requires source/citation/trust authority gates.
