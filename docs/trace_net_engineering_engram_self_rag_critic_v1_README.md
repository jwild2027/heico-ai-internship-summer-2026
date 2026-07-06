# TRACE-Net Engineering Engram Self-RAG Critic v1

H28 adds an artifact-only Self-RAG-style critic for targeted Engram overlay answer-smoke results.

## Purpose

The critic reviews answer-smoke records after retrieved Engram overlays have been injected into the real answer-smoke prompt path. It checks whether the answer stayed within the source-trace boundary, used counted citations when proof context exists, avoided summaries-as-proof, avoided unsupported claims, and avoided answer permission.

## Safety contract

- No LLM calls.
- No Postgres writes.
- No Qdrant reads or writes.
- No OpenSearch writes or uploads.
- No source-truth mutation.
- No answer permission.
- Engram and critic memories remain behavior guidance only, not proof.

## Typical build

```bash
python -B scripts/build_trace_net_engineering_engram_self_rag_critic_v1.py \
  --answer-smoke local_data/organization/trace_net/llm_h27e_overlay_target_q12_q16_q18_q25_q29/trace_net_engineering_llm_answer_smoke_v1.json \
  --output-dir local_data/organization/trace_net/engineering_engram_self_rag_critic_v1 \
  --min-records 5 \
  --min-critic-pass-or-expected 5 \
  --max-repair-recommended 0 \
  --require-source-quality-pass \
  --require-no-answer-permission \
  --max-unsafe 0 \
  --max-write-attempts 0
```

## Next step

H29 can add CRAG Engram repair for records with `REVIEW` or `REPAIR_RECOMMENDED` status.
