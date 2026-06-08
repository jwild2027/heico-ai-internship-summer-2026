# TRACE-Net Layer Confidence Stage 5a Controlled Rollout

This patch adds the first safe confidence-policy-controlled artifact.

Stage 5a applies the Stage 3 layer-specific confidence policy only to low-risk layers:

- `source_trace`
- `part_catalog`

All other Evidence Consensus layers remain on the existing rule-based trust/RAG routing in this artifact. The primary Evidence Consensus records are not overwritten.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_confidence_stage5.py \
  tests/unit/test_tiff_trace_net_confidence_stage5_quality.py \
  -q
```

## Build controlled artifact

```bash
python scripts/build_trace_net_confidence_stage5_control.py --open
```

Outputs:

```text
local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_controlled_records.jsonl
local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_control_summary.json
local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_control_report.md
local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_control_report.html
```

## Quality gate

```bash
python scripts/check_trace_net_confidence_stage5_quality.py \
  --write-json \
  --min-records 1813 \
  --min-pages 509 \
  --required-controlled-layers source_trace,part_catalog \
  --max-unsafe-policy-rag-include-records 0 \
  --max-non-controlled-changed-records 0 \
  --min-source-trace-policy-A-records 509 \
  --min-part-catalog-policy-A-records 360 \
  --max-table-candidate-direct-rag-records 0 \
  --max-visual-text-above-B-records 0
```

## Why this is safe

The policy controls only deterministic evidence layers first:

```text
source_trace -> include_as_source_evidence when source/page/TIFF graph evidence is present
part_catalog -> include_as_verified_part_evidence when source trace + catalog support agree
```

The following layers stay rule-controlled for now:

```text
visual_text
table_candidate
table_tiles
table_tile_text_refined
```

This lets us observe policy-controlled output without letting model-derived or preprocessing-only evidence change RAG routing yet.
