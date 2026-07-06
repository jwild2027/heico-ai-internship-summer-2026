# TRACE-Net Ask API Hybrid Retrieval v3 Routing v1

This module exposes the PASS Hybrid Retrieval v3 artifact as a read-only, OpenAI-compatible API routing layer.

## Purpose

Hybrid Retrieval v3 adds CRAG-aware corrective routing metadata to Hybrid Retrieval v2 results. This API lets Open WebUI or local curl tests ask against that Hybrid v3 routing artifact while preserving TRACE-Net's final-answer safety boundary.

## Inputs

- `local_data/organization/trace_net/hybrid_retrieval_v3/trace_net_hybrid_retrieval_v3.json`
- Optional final gate artifact:
  - `local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json`
  - `local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1_answer.md`

## Outputs

- `local_data/organization/trace_net/ask_api_hybrid_v3_routing/trace_net_ask_api_hybrid_v3_routing_v1.json`
- `trace_net_ask_api_hybrid_v3_routing_v1_quality.json`
- `trace_net_ask_api_hybrid_v3_routing_v1_summary.json`
- `trace_net_ask_api_hybrid_v3_routing_v1_manifest.json`

## Safety contract

- Hybrid v3 routing groups can guide retrieval/review only.
- Hybrid v3 routing groups cannot answer directly or prove claims.
- Corrective actions are routing metadata, never proof.
- Final answers are returned only when an existing final-gate artifact authorizes the exact query.
- No Postgres, Qdrant, OpenSearch, graph, source, citation, or trust writes occur.

## Open WebUI

Base URL:

```text
http://host.docker.internal:8015/v1
```

Model:

```text
trace-net-hybrid-v3-routing-v1
```

API key: blank, unless `TRACE_NET_ASK_API_KEY` is configured.
