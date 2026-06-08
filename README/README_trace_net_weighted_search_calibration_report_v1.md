# TRACE-Net Weighted Search Calibration Report v1

This patch adds a simulation/explainability layer for weighted search results.

It reads the latest weighted search simulation and the official weights policy, then explains:

- which pages were adjusted by validated feedback
- which feedback adjustments hit the cap
- whether rank changed
- whether evidence diversity/verified evidence preserved rank despite negative feedback
- how much extra demotion/boost would be needed to change adjacent rank positions
- whether unsafe/excluded/source-truth-mutation conditions appeared

It is report-only. It does not change production ranking, source truth, trust tiers, RAG eligibility, Evidence Consensus, or feedback policy signals.

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
  --min-calibration-records 1 \
  --min-feedback-adjusted-records 1 \
  --max-unsafe-records 0 \
  --max-excluded-records 0 \
  --max-source-truth-mutations 0 \
  --max-context-warning-signals-used 0 \
  --require-policy-version trace_net_weights_policy_v1 \
  --require-gap-analysis
```

Use `--min-rank-changed-records 1` only for test queries where rank movement is expected. For the known `120-50645-009` case, feedback changes scores but may not change rank because verified evidence diversity can still outweigh one negative feedback event.
