# TRACE-Net Fast Answer Composer v1

`trace_net_fast_answer_composer_v1` turns a passing anchor-aware graph/Leiden context pack into a deterministic, citation-heavy answer for exact part-number questions.

It is designed for fast chat / WebUI use where direct exact anchors already exist. It avoids sending a huge prompt to Gemma for exact part lookup.

## Inputs

- `trace_net_anchor_aware_graph_leiden_expander_v1.json`
- Optional explicit question and part number

## Outputs

- `trace_net_fast_answer_composer_v1.json`
- `trace_net_fast_answer_composer_v1_answer.md`
- `trace_net_fast_answer_composer_v1_records.csv`
- `trace_net_fast_answer_composer_v1_records.jsonl`
- `trace_net_fast_answer_composer_v1_citation_map.jsonl`
- `trace_net_fast_answer_composer_v1_violations.jsonl`
- `trace_net_fast_answer_composer_v1_quality_check.json` when `--quality` is used

## Safety contract

- Dry-run only
- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- Graph/Leiden evidence is treated only as nearby context, not proof of identity
