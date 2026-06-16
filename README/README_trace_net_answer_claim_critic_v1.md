# TRACE-Net Answer Claim Critic v1

`trace_net_answer_claim_critic_v1` is the third safe Self-RAG-style critic layer.

It reads:

- Dynamic Final-Gate Execution v1
- Evidence Sufficiency Critic v1
- Retrieval Critic v1

and produces read-only critic records for final/dynamic answer text and individual claims.

## Safety contract

The Answer Claim Critic can flag wording and claim-support issues. It cannot:

- answer directly
- prove claims
- mutate source truth
- write Postgres
- write Qdrant
- write OpenSearch
- turn feedback/community/category/retrieval-only records into proof

## Main checks

The critic checks for:

- missing citation references
- retrieval-only proof language
- feedback used as proof
- Leiden/community used as proof
- category used as proof
- local path leaks
- raw bytes representation leaks
- source-truth mutation language
- overstatement language
- OCR overconfidence wording
- evidence/retrieval critic audit requirements

## Build

```bash
python scripts/build_trace_net_answer_claim_critic_v1.py \
  --dynamic-final-gate local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json \
  --evidence-sufficiency-critic local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json \
  --retrieval-critic local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json \
  --output-dir local_data/organization/trace_net/answer_claim_critic \
  --min-answer-records 5 \
  --min-queries 5 \
  --min-claim-records 1 \
  --require-dynamic-final-gate-quality-pass \
  --require-evidence-sufficiency-quality-pass \
  --require-retrieval-critic-quality-pass \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_answer_claim_critic_v1_quality.py \
  --report-path local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json \
  --min-answer-records 5 \
  --min-queries 5 \
  --min-claim-records 1 \
  --require-dynamic-final-gate-quality-pass \
  --require-evidence-sufficiency-quality-pass \
  --require-retrieval-critic-quality-pass \
  --write-json
```

## Outputs

- `trace_net_answer_claim_critic_v1.json`
- `trace_net_answer_claim_critic_v1_records.jsonl`
- `trace_net_answer_claim_critic_v1_claims.jsonl`
- `trace_net_answer_claim_critic_v1_summary.json`
- `trace_net_answer_claim_critic_v1_quality.json`
- `trace_net_answer_claim_critic_v1_manifest.json`
- `trace_net_answer_claim_critic_v1.md`
- `trace_net_answer_claim_critic_v1.html`
