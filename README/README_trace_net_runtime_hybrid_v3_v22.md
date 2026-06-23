# TRACE-Net Runtime Hybrid v3 v2.2

This module makes the current working TRACE-Net path the default local runtime:

```text
Open WebUI
  -> TRACE-Net final-return policy Hybrid v3 v2.2 API on port 8016
  -> Hybrid Retrieval v3 artifact
  -> final-answer gate artifact
```

It is a runtime launcher and manifest builder, not a retriever and not an answer
authority.

## Safety contract

The runtime layer is read-only with respect to TRACE-Net evidence state:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission from runtime routing
- no claim-proof authority from Hybrid v3 routing
- final gate remains the answer authority

Docker service starts are allowed operational actions, but they are not evidence
writes and do not mutate source truth.

## Main commands

Build the runtime manifest:

```bash
python scripts/build_trace_net_runtime_hybrid_v3_v22.py \
  --hybrid-v3-report local_data/organization/trace_net/hybrid_retrieval_v3/trace_net_hybrid_retrieval_v3.json \
  --final-return-config local_data/organization/trace_net/ask_api_final_return_policy_hybrid_v3_v22/trace_net_ask_api_final_return_policy_hybrid_v3_v22.json \
  --final-answer-report local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json \
  --final-answer-markdown local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1_answer.md \
  --output-dir local_data/organization/trace_net/runtime_hybrid_v3_v22 \
  --model-name trace-net-final-return-policy-hybrid-v3-v2.2 \
  --port 8016 \
  --require-hybrid-v3-quality-pass \
  --quality
```

Start the default runtime:

```bash
python scripts/run_trace_net_runtime_hybrid_v3_v22.py \
  --start-docker \
  --check-services \
  --require-hybrid-v3-quality-pass
```

Open WebUI settings:

```text
Base URL: http://host.docker.internal:8016/v1
Model: trace-net-final-return-policy-hybrid-v3-v2.2
API Key: blank
```
