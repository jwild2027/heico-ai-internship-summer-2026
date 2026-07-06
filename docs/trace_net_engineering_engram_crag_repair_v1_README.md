# TRACE-Net Engineering Engram CRAG Repair v1

H29 adds an artifact-only CRAG repair loop for the Engineering Engram path.

## Purpose

The module consumes H28 Self-RAG critic records and the source answer-smoke manifest. It decides whether each answer should be preserved, treated as an expected unknown/no-proof boundary, or repaired.

## Safety contract

- CRAG may repair answer behavior, formatting, and citation discipline.
- CRAG cannot create proof.
- Engram memory and summaries remain guidance only.
- No answer permission is granted.
- No Postgres, Qdrant, or OpenSearch writes occur in this artifact mode.
- Expected unknown/no-proof partials are preserved rather than over-repaired.

## Typical command

```bash
python -B scripts/build_trace_net_engineering_engram_crag_repair_v1.py \
  --critic local_data/organization/trace_net/engineering_engram_self_rag_critic_v1/trace_net_engineering_engram_self_rag_critic_v1.json \
  --answer-smoke local_data/organization/trace_net/llm_h27e_overlay_target_q12_q16_q18_q25_q29/trace_net_engineering_llm_answer_smoke_v1.json \
  --output-dir local_data/organization/trace_net/engineering_engram_crag_repair_v1 \
  --min-records 5 \
  --min-crag-pass-or-no-repair 5 \
  --max-repair-attempts 0 \
  --require-source-quality-pass \
  --require-critic-quality-pass \
  --require-no-answer-permission \
  --max-unsafe 0 \
  --max-write-attempts 0
```
