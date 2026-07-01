# TRACE-Net Figure/Item Fast Answer Composer v1

Builds a deterministic cited answer for cached figure/item questions such as `Show figure 85 item 1`.

## Inputs

- Anchor-aware graph/Leiden context pack JSON.
- Question text, plus optional `--figure` and `--item` overrides.

## Outputs

- `trace_net_figure_item_fast_answer_composer_v1.json`
- `trace_net_figure_item_fast_answer_composer_v1_answer.md`
- `trace_net_figure_item_fast_answer_composer_v1_records.csv`
- `trace_net_figure_item_fast_answer_composer_v1_quality_check.json`

## Safety contract

Dry-run only. No Postgres, Qdrant, or OpenSearch writes. No source-truth mutation. No answer permission.
