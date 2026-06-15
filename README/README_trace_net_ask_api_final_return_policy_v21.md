# TRACE-Net Ask API Final Return Policy v2.1

This module is the conservative return-policy layer for dynamic TRACE-Net answering.

It combines:

- Dynamic Final-Gate Execution v1
- Retrieval Critic v1
- Evidence Sufficiency Critic v1
- Answer Claim Critic v1
- optional Ask API Dynamic Retrieval v2 config

A final answer is returned only when all gates and critics agree and all hard safety counters are zero.
Otherwise the policy returns audit-required, retrieval-only, blocked, or no-safe-answer status.

Safety contract:

- read-only controller
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- policy records cannot answer directly
- policy records cannot prove claims
- feedback/community/category/retrieval-only signals never become proof

## Build

```bash
python scripts/build_trace_net_ask_api_final_return_policy_v21.py \
  --dynamic-final-gate local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json \
  --retrieval-critic local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json \
  --evidence-sufficiency-critic local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json \
  --answer-claim-critic local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json \
  --ask-api-dynamic local_data/organization/trace_net/ask_api_dynamic_retrieval_v2/trace_net_ask_api_dynamic_retrieval_v2.json \
  --output-dir local_data/organization/trace_net/ask_api_final_return_policy_v21 \
  --min-policy-records 5 \
  --min-queries 5 \
  --min-return-allowed 1 \
  --require-dynamic-final-gate-quality-pass \
  --require-retrieval-critic-quality-pass \
  --require-evidence-sufficiency-quality-pass \
  --require-answer-claim-critic-quality-pass \
  --build-only \
  --quality
```

## Serve

```bash
python scripts/run_trace_net_ask_api_final_return_policy_v21.py \
  --output-dir local_data/organization/trace_net/ask_api_final_return_policy_v21 \
  --host 0.0.0.0 \
  --port 8014
```

OpenAI-compatible base URL:

```text
http://host.docker.internal:8014/v1
```

Model:

```text
trace-net-final-return-policy-v2.1
```
