# TRACE-Net v2 summary guidance index v1

Builds a guidance-only index from page-level v2/page-context summaries.

## Contract

- V2 summaries are guidance only.
- Summaries may guide planning/page selection/answer framing.
- Summaries must not prove final factual claims.
- Output records set `guidance_only=true` and `answer_permission=false`.
- No Postgres/Qdrant/OpenSearch writes.
- No source-truth mutation.

## Outputs

- `trace_net_v2_summary_guidance_index_v1.json`
- `trace_net_v2_summary_guidance_index_v1_quality_check.json`
- `trace_net_v2_summary_guidance_index_v1_records.csv`

## Next module

`trace_net_engineering_query_planner_v1` should consume this index to create route plans.
