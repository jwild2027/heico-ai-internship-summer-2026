# TRACE-Net WebUI Self-RAG / CRAG Bridge v1

This module runs the current engineering-brain artifact stages for one WebUI-style question and writes a checklist proving which gates were actually executed.

## Purpose

The current TRACE-Net WebUI endpoint can answer through gated lookup / fallback paths without running the full engineering-brain sequence. This bridge makes the missing gates visible by running:

1. engineering query planner
2. context-pack blueprint
3. context-pack builder
4. Self-RAG evidence check
5. CRAG retry planner

CRAG is always evaluated. If Self-RAG does not require retry, the checklist records `crag_retry: skipped_not_needed` instead of falsely saying CRAG was used.

## Inputs

Typical local artifact inputs:

- `local_data/organization/trace_net/engineering_reasoning_kernel/trace_net_engineering_reasoning_kernel_v1.json`
- `local_data/organization/trace_net/fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json`
- `local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json`
- `local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json`
- `local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json`
- `local_data/organization/trace_net/image_visual_observer/trace_net_image_visual_observer_v1.json`

Missing optional artifact inputs are reported as `input_missing` or `not_configured`.

## Outputs

The main report is:

```text
local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1.json
```

It also writes:

- `trace_net_webui_self_rag_crag_bridge_v1_summary.json`
- `trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl`
- `trace_net_webui_self_rag_crag_bridge_v1_checklist.txt`
- stage reports under `stage_reports/`

## Safety contract

This bridge is artifact-only and pre-answer:

- no Gemma call
- no final answer draft
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission

## Example

```bash
python scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py \
  --question "Find part number 120-29073-001 and nearby similar parts. Use every TRACE-Net evidence route that is available and show source boundaries." \
  --kernel local_data/organization/trace_net/engineering_reasoning_kernel/trace_net_engineering_reasoning_kernel_v1.json \
  --route-dispatch-handoff local_data/organization/trace_net/fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json \
  --table-exact-search-adapter local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json \
  --page-context-v2 local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json \
  --leiden-communities local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json \
  --image-visual-observer local_data/organization/trace_net/image_visual_observer/trace_net_image_visual_observer_v1.json \
  --output-dir local_data/organization/trace_net/webui_self_rag_crag_bridge \
  --quality
```
