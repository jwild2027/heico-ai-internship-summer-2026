# TRACE-Net Ask Feedback Mode v1

Adds feedback modes to `trace_net_ask.py`.

Modes:

- `--feedback-mode off`: default deterministic ask path.
- `--feedback-mode simulate`: runs the normal ask path, then feedback-aware search simulation and feedback-aware answer simulation.
- `--feedback-mode apply`: intentionally blocked in v1.

The simulation mode is advisory only. It does not mutate production search ranking, Evidence Consensus, source truth, trust tiers, or RAG eligibility.

Example:

```bash
python scripts/trace_net_ask.py \
  --part-number 120-50645-009 \
  --top-k 10 \
  --feedback-mode simulate \
  --open
```

Quality:

```bash
python scripts/check_trace_net_ask_quality.py \
  --write-json \
  --min-answer-pages 1 \
  --min-evidence-records 1 \
  --max-unsafe-answer-groups 0 \
  --require-feedback-mode simulate \
  --require-feedback-simulation \
  --min-feedback-signals-used 1 \
  --min-feedback-groups-adjusted 1 \
  --min-feedback-rank-changed-records 1 \
  --max-feedback-unsafe-groups 0 \
  --max-feedback-context-warning-signals-used 0
```
