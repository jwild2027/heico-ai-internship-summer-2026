# TRACE-Net Layer Confidence Stage 5a Policy Control

Stage 5a is the first limited rollout of TRACE-LC policy-controlled routing.
It creates a policy-controlled view of Evidence Consensus records, but only for
low-risk deterministic layers by default:

```text
source_trace
part_catalog
```

All other layers remain rule-controlled:

```text
visual_text
table_candidate
table_tiles
table_tile_text_refined
```

This lets the project prove policy control safely before it changes broader
RAG/repair behavior.

## Build the controlled view

```bash
python scripts/build_trace_net_confidence_policy_control.py --open
```

## Quality gate

```bash
python scripts/check_trace_net_confidence_stage5_quality.py \
  --write-json \
  --min-records 1813 \
  --min-pages 509 \
  --min-policy-controlled-records 873 \
  --require-controlled-layers source_trace,part_catalog \
  --min-source-trace-final-A-records 509 \
  --max-unsafe-final-rag-include-records 0 \
  --max-controlled-routing-changed-records 0
```

The expected behavior for the current corpus is that source-trace and
part-catalog remain safe, and no unsafe records enter RAG.
