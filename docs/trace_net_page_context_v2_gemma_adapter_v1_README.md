# TRACE-Net Page Context V2 Gemma Adapter v1

This patch keeps the existing TRACE-Net V2 graph convention and adapts the new Gemma4 V2 summary runner output into the old `page_context_v2` artifact shape.

It preserves the old graph contract:

```text
page:<page_id> -[:HAS_CONTEXT_V2]-> page_context_v2:<page_id>
```

## Inputs

A Gemma V2 summary runner output JSON/JSONL, normally:

```text
local_data/organization/trace_net/v2_gemma_summary_full_server_v1/full_509/trace_net_v2_gemma_summary_sample_runner_v1.json
```

## Outputs

By default, artifacts are written under:

```text
local_data/organization/trace_net/page_context_v2/
```

Files:

```text
trace_net_page_context_v2_records.json
trace_net_page_context_v2_records.jsonl
trace_net_page_context_v2_graph_nodes.json
trace_net_page_context_v2_graph_edges.json
trace_net_page_context_v2_gemma_adapter_v1.json
trace_net_page_context_v2_gemma_adapter_v1_quality_check.json
```

## Safety contract

The adapter is non-mutating and writes local artifacts only. It does not write to Postgres, Qdrant, or OpenSearch. V2 records are guidance only and cannot answer directly or prove claims without source-truth evidence.
