# TRACE-Net Weighted Search Calibration Report v1

Builds an explainability report for the latest TRACE-Net weighted search simulation.

It explains:

- score component contribution per page group
- feedback boost/demotion contribution
- whether feedback hit the configured cap
- whether feedback changed rank
- how much additional demotion/boost would be needed to change adjacent rank
- whether evidence diversity preserved rank despite negative feedback

This is report-only. It does not mutate production ranking, source truth, Evidence Consensus, RAG eligibility, trust tiers, or feedback records.

## Run

```bash
python scripts/build_trace_net_weighted_search_calibration.py --open
```

## Quality

```bash
python scripts/check_trace_net_weighted_search_calibration_quality.py \
  --write-json \
  --min-records 1 \
  --min-pages 1 \
  --min-component-breakdown-records 1 \
  --min-rank-comparison-records 1 \
  --min-feedback-adjusted-records 1 \
  --max-unsafe-records 0 \
  --max-excluded-records 0 \
  --max-source-truth-mutations 0 \
  --max-context-warning-signals-used 0
```

For the current `120-50645-009` case, use the stricter cap/margin checks if desired:

```bash
python scripts/check_trace_net_weighted_search_calibration_quality.py \
  --write-json \
  --min-records 3 \
  --min-pages 3 \
  --min-component-breakdown-records 3 \
  --min-rank-comparison-records 3 \
  --min-feedback-adjusted-records 1 \
  --min-feedback-cap-hit-records 1 \
  --min-demotion-shortfall-records 1 \
  --max-unsafe-records 0 \
  --max-excluded-records 0 \
  --max-source-truth-mutations 0 \
  --max-context-warning-signals-used 0
```

## Outputs

```text
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration.json
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration_records.jsonl
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration_summary.json
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration_report.md
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration_report.html
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration_graph_nodes.json
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration_graph_edges.json
local_data/organization/trace_net/weighted_search_calibration/trace_net_weighted_search_calibration_quality.json
```
