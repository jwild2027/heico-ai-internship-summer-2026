# TRACE-Net Ask API Final Return Policy Hybrid v3 v2.2

This module promotes Hybrid Retrieval v3 from a separate routing endpoint into a final-return-policy controller.

It reads Hybrid Retrieval v3 groups directly, uses them as retrieval-routing context, and still requires final-gate authorization before any final answer may be returned.

## Safety contract

- Hybrid v3 routing groups are not proof.
- Corrective actions are not proof.
- Retrieval-only groups cannot answer directly.
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- Final answers require final-gate authorization.

## Main artifacts

Input:

- `local_data/organization/trace_net/hybrid_retrieval_v3/trace_net_hybrid_retrieval_v3.json`
- `local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json`
- optional final answer markdown

Output:

- `local_data/organization/trace_net/ask_api_final_return_policy_hybrid_v3_v22/trace_net_ask_api_final_return_policy_hybrid_v3_v22.json`
- quality, summary, and manifest JSON files

## Server

Default port: `8016`

Open WebUI:

- Base URL: `http://host.docker.internal:8016/v1`
- Model: `trace-net-final-return-policy-hybrid-v3-v2.2`
- API key: blank unless configured
