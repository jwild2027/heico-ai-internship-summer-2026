# TRACE-Net Vision Model Pilot v1 Selection Refinement

This patch tightens the Step 16.2 vision-model pilot selection logic.

The key rule is:

```text
Ink/layout calibration is stronger than broad visual labels.
```

So a page is no longer sent to the vision-model pilot merely because an older broad classifier marked it as a chart/figure candidate. In particular:

```text
confirmed blank pages are skipped by default
text-heavy pages are skipped by default
plain table/grid pages stay in table routes unless explicitly visual/mixed
```

Manual override remains available with `--include-pages` for targeted review.

Safety behavior is unchanged:

```text
vision output is advisory only
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
final_answer_allowed = false
```
