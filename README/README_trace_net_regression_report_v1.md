# TRACE-Net Fixed Regression Report v1

Builds a consolidated dashboard from `local_data/organization/trace_net/regression/fixed_set_v1/*` case artifacts.

## Build

```bash
python scripts/build_trace_net_regression_report.py --open
```

## Quality

```bash
python scripts/check_trace_net_regression_report_quality.py \
  --write-json \
  --min-cases 7 \
  --max-failing-cases 0 \
  --max-unsafe-answer-cases 0 \
  --max-weighted-unsafe-cases 0 \
  --max-source-truth-mutation-cases 0 \
  --max-context-warning-used-cases 0
```

Outputs are written under:

```text
local_data/organization/trace_net/regression/fixed_set_v1/
```

Files:

```text
regression_summary.json
regression_records.jsonl
regression_report.md
regression_report.html
regression_graph_nodes.json
regression_graph_edges.json
regression_quality.json
```
