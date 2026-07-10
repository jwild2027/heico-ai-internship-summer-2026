# TRACE-Net Gated Visual Endpoint Context v1

This patch creates an endpoint/router-ready payload from the gated visual
retrieval documents.

## Purpose

The live answer endpoint/router should not consume the old raw 185-page visual
context set. It should consume the gated output:

```text
104 confirmed search-ready visual docs
81 review-only visual candidate docs, counted but not used automatically
```

This adapter turns the confirmed docs into route context payloads:

```text
endpoint_payload_type = trace_net_route_context
route_name = gated_image_visual
```

## Inputs

```text
local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/
  trace_net_gated_visual_retrieval_documents_v1_1.jsonl
```

Optional review-only input:

```text
local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/
  trace_net_gated_visual_candidate_review_documents_v1_1.jsonl
```

## Output

```text
trace_net_gated_visual_endpoint_context_v1.jsonl
trace_net_gated_visual_endpoint_context_v1_report.txt
summary.json
```

## Safety

The payload does not answer directly:

```text
final_answer_allowed=false
answer_permission=false
can_answer_directly=false
can_prove_claims=false
```

Visual context remains candidate retrieval guidance only.
