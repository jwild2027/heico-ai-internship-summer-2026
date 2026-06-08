# TRACE-Net Layer Confidence Stage 2

Stage 1 writes advisory TRACE-LC scores onto every Evidence Consensus record. Stage 2 compares those advisory confidence tiers with the current rule-based trust tiers.

This does not change routing or RAG eligibility. It produces a calibration/evaluation report so the score policy can be tuned before it controls any decisions.

## Run

```bash
python scripts/evaluate_trace_net_confidence_stage2.py --open
```

Outputs:

```text
local_data/organization/trace_net/confidence/trace_lc_stage2_eval.json
local_data/organization/trace_net/confidence/trace_lc_stage2_eval.md
local_data/organization/trace_net/confidence/trace_lc_stage2_eval.html
```

## Quality

```bash
python scripts/check_trace_net_confidence_stage2_quality.py \
  --write-json \
  --min-records 1813 \
  --min-layers 6 \
  --max-missing-confidence-records 0
```

## What it measures

- Current rule tier versus TRACE-LC confidence tier.
- Confusion matrix between trust tiers and confidence tiers.
- Per-layer agreement.
- Current RAG includes with low confidence.
- Current RAG excludes with high confidence.
- Source-trace records that score below confidence tier A.
- Samples of promotion/demotion candidates.

The expected first result is many disagreements, especially for source-trace records. That is not a failure. It means Stage 3 should introduce layer-specific thresholds and/or special source-trace scoring before confidence tiers control routing.
