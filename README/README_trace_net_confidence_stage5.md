# TRACE-Net Layer Confidence Stage 5a policy control

This patch starts using the layer-specific TRACE-LC confidence policy for the
lowest-risk layers only:

- `source_trace`
- `part_catalog`

It does not mutate the main Evidence Consensus records. It writes a controlled
decision view under:

```text
local_data/organization/trace_net/confidence/stage5_control/
```

The original consensus file remains the audit source of truth.

## Run

```bash
python scripts/build_trace_net_confidence_stage5_control.py --open
```

## Quality

```bash
python scripts/check_trace_net_confidence_stage5_quality.py \
  --write-json \
  --min-records 1813 \
  --min-pages 509 \
  --min-controlled-records 873 \
  --min-source-trace-policy-A-records 509 \
  --min-part-catalog-policy-A-records 362 \
  --max-unsafe-stage5-rag-include-records 0 \
  --max-table-candidate-direct-rag-records 0 \
  --max-visual-text-controlled-records 0
```

## Purpose

Stage 5a lets future RAG/readiness code consume policy-selected decisions for
safe layers while keeping visual/table-derived layers rule-gated.

Controlled now:

```text
source_trace -> policy selected source truth
part_catalog -> policy selected verified part evidence
```

Still rule-retained:

```text
visual_text
table_candidate
table_tiles
table_tile_text_refined
```
