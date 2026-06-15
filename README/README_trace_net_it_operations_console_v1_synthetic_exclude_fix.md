# TRACE-Net IT Operations Console v1 Synthetic Artifact Exclude Fix

This patch keeps the real IT operations console from counting synthetic issue-origin test fixtures as real project health failures.

By default, scans of `local_data/organization/trace_net` exclude:

- `it_issue_origin_test_matrix/synthetic_trace_net_root/`
- `it_issue_origin_test_matrix/synthetic_console_report/`

The synthetic test matrix still works because it scans the synthetic root directly. For diagnostics, the console can include these nested synthetic artifacts with:

```bash
python scripts/build_trace_net_it_operations_console_v1.py \
  --trace-net-root local_data/organization/trace_net \
  --output-dir local_data/organization/trace_net/it_operations_console \
  --include-synthetic-test-artifacts \
  --quality
```

Default real-project scan:

```bash
python scripts/build_trace_net_it_operations_console_v1.py \
  --trace-net-root local_data/organization/trace_net \
  --output-dir local_data/organization/trace_net/it_operations_console \
  --max-critical-issues 0 \
  --quality
```
