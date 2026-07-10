# TRACE-Net V2 sample runner simple v1

Laptop-safe runner for a 5-page sample from the existing V2 guide.

It imports `tiff.trace_net_page_context_v2` and uses the existing `heuristic_context_v2`, `build_prompt`, and `sanitize_context_v2` helpers. It does not rewrite V2, does not call Postgres/Qdrant/OpenSearch, and does not grant answer permission.

Outputs:

- `trace_net_v2_sample_runner_simple_v1.json`
- `trace_net_v2_sample_runner_simple_v1_records.jsonl`
- `trace_net_v2_sample_runner_simple_v1_prompts.jsonl`
- `trace_net_v2_sample_runner_simple_v1.md`

Each record also includes a report-only `v3_preview` showing possible future V3 fields: Engram guidance, Leiden guidance, and Dublin Core metadata.
