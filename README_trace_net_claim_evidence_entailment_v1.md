# TRACE-Net Claim Evidence Entailment v1

Read-only Self-RAG-style expansion module for advisory claim-to-citation/evidence checking.

## Purpose

This module strengthens the TRACE-Net critic stack by creating per-claim advisory records for:

- claim-to-citation/evidence lexical entailment scoring
- per-claim best evidence span matching
- Dublin Core source identity resolution for cited page IDs
- simple contradiction-risk detection across claims in the same query
- critic disagreement detection across retrieval/evidence/answer critics
- candidate human-review escalation records for weak or risky claims

It is intentionally not an answer gate. It cannot prove claims and cannot answer directly.

## Inputs

Typical inputs:

- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json`
- `local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json`
- `local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json`
- `local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json`
- `local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json`

Only the dynamic final gate is required. The other inputs improve scoring and trace richness.

## Outputs

- `trace_net_claim_evidence_entailment_v1.json`
- `trace_net_claim_evidence_entailment_v1_quality.json`
- `trace_net_claim_evidence_entailment_v1.md`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
- human-review escalation records are candidates only; this module does not write the human review queue

## Example

```bash
python scripts/build_trace_net_claim_evidence_entailment_v1.py \
  --dynamic-final-gate local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json \
  --dublin-core-source-package-extension local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json \
  --hybrid-v2-report local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json \
  --retrieval-critic local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json \
  --evidence-sufficiency-critic local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json \
  --answer-claim-critic local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json \
  --output-dir local_data/organization/trace_net/claim_evidence_entailment \
  --min-entailment-records 1 \
  --min-claim-records 1 \
  --min-queries 1 \
  --require-dynamic-final-gate-quality-pass \
  --require-dublin-core-source-quality-pass \
  --quality
```
