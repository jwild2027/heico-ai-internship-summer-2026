# TRACE-Net IT Operations Console v1 self-output exclude fix

This patch prevents the real IT Operations Console from scanning its own prior output directory by default.

## Why

When the console scans `local_data/organization/trace_net` and writes its own report under:

```text
local_data/organization/trace_net/it_operations_console/
```

an older failed console report can be picked up as a project artifact. That creates a self-referential failure:

```text
IT console fails because it found an old IT console FAIL artifact.
```

This is not a real pipeline issue. It is an operations-console scanning boundary issue.

## Behavior after this patch

By default, the console excludes its selected output directory when that output directory is inside the scanned TRACE-Net root.

The existing synthetic issue-origin exclusions are preserved.

A new diagnostic override is available:

```bash
--include-output-dir-artifacts
```

Use that only when intentionally debugging the console output artifacts themselves.

## Expected result

After applying the patch, rerunning the real console should remove the self-referential criticals:

```text
stage_quality_failed: it_operations_console
raw_feedback_direct_to_llm_issue_count from it_operations_console summary
source_truth_mutation_issue_count from it_operations_console summary
```

Warnings/review backlog from real project stages may remain and are useful for IT review.
