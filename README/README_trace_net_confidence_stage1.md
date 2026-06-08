# TRACE-Net Layer Confidence Stage 1

This patch adds advisory TRACE-LC confidence scoring to the TRACE-Net Evidence Consensus Router.

It is non-breaking:

- Existing trust tiers remain the active routing decision.
- Existing RAG actions remain unchanged.
- New confidence fields are written for review, calibration, and future routing experiments.

## New per-record field

Each evidence consensus record now includes:

```json
"confidence_scores": {
  "version": "trace_lc_v1",
  "source_trace_score": 1.0,
  "graph_support_score": 0.9,
  "ocr_support_score": 0.65,
  "part_catalog_score": 0.75,
  "extraction_layer_score": 0.8,
  "support_score": 0.82,
  "risk_score": 0.05,
  "usable_confidence": 0.779,
  "confidence_tier": "B",
  "max_allowed_tier": "A",
  "hard_gate_blocked": false,
  "hard_gate_reasons": [],
  "weights": {...},
  "thresholds": {...}
}
```

## Formula

```text
support_score =
  0.30 * source_trace_score +
  0.25 * graph_support_score +
  0.20 * ocr_support_score +
  0.20 * part_catalog_score +
  0.05 * extraction_layer_score

usable_confidence = support_score * (1 - risk_score)
```

Hard gates are recorded but do not yet override routing beyond the existing v1.1 trust logic.

## New summary fields

```text
confidence_version
confidence_score_records
confidence_tier_counts
confidence_avg_usable
confidence_avg_support
confidence_avg_risk
confidence_tier_disagreement_records
confidence_hard_gate_blocked_records
confidence_weights
confidence_thresholds
```

## Run

```bash
python scripts/build_trace_net_evidence_consensus.py \
  --expect-pages 509 \
  --samples 25 \
  --open
```

Quality gate with confidence required:

```bash
python scripts/check_trace_net_evidence_consensus_quality.py \
  --write-json \
  --min-pages 509 \
  --min-records 1813 \
  --require-source-trace \
  --min-visual-text-records 25 \
  --min-table-tile-records 286 \
  --min-table-tile-text-refined-records 120 \
  --require-confidence-scores
```

## Stage 1 intent

Stage 1 is observation-only. Use it to compare rule-based trust tiers against score-based tiers before allowing confidence scores to control RAG routing.
