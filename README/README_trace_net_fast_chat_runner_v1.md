# TRACE-Net Fast Chat Runner v1

This version integrates the fast chat multi-route quality gate directly into the runner.

## Purpose

The runner accepts a user question and a cached anchor-aware context pack, chooses the correct fast route, composes an answer, then runs route-specific validation before marking an answer as WebUI-ready.

Implemented routes:

- `exact_part_number` -> fast exact part answer composer + exact answer quality gate + multi-route gate
- `figure_or_item` -> figure/item fast answer composer + multi-route gate
- `part_family` -> part-family fast answer composer + multi-route gate

Planned routes remain safe placeholders:

- `image_or_diagram`
- `plain_text`

## Safety contract

The runner is dry-run only:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no human review requirement

## Main files

- `tiff/trace_net_fast_chat_runner_v1.py`
- `scripts/run_trace_net_fast_chat_runner_v1.py`
- `scripts/check_trace_net_fast_chat_runner_v1_quality.py`

## Example

```bash
python scripts/run_trace_net_fast_chat_runner_v1.py \
  --question "Show the 120-29073 family." \
  --context-pack local_data/organization/trace_net/anchor_aware_graph_leiden_expander_gemma4_native_001/trace_net_anchor_aware_graph_leiden_expander_v1.json \
  --output-dir local_data/organization/trace_net/fast_chat_runner_part_family_120_29073_integrated_gate \
  --require-source-quality-pass \
  --require-multi-route-quality-pass \
  --require-webui-answer-ready \
  --quality
```
