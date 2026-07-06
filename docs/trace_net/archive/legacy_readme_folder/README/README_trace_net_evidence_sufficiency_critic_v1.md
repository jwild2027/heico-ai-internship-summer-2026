# TRACE-Net Evidence Sufficiency Critic v1

TRACE-Net Evidence Sufficiency Critic v1 is a read-only Self-RAG-style critic layer.

It sits after:

```text
Hybrid Retrieval v2
-> Dynamic Final-Gate Execution v1
-> Retrieval Critic v1
-> Evidence Sufficiency Critic v1
```

The Retrieval Critic asks whether retrieval looked good enough. The Evidence Sufficiency Critic asks whether the retrieved/final-gate evidence has enough source trace, citation, and authority to be used by the final gate.

## Safety contract

The critic can recommend actions, but it cannot answer or prove claims.

It always keeps:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
```

It also blocks these as proof:

```text
feedback
community labels
category labels
retrieval-only records
raw OCR
raw visual output
raw feedback
unsafe/debug/prompt records
```

## Inputs

Default inputs:

```text
local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json
local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json
local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json
```

## Outputs

```text
local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json
local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1_records.jsonl
local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1_summary.json
local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1_quality.json
local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1_manifest.json
local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.md
local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.html
```

## Build

```bash
python scripts/build_trace_net_evidence_sufficiency_critic_v1.py \
  --hybrid-v2-report local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json \
  --dynamic-final-gate local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json \
  --retrieval-critic local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json \
  --output-dir local_data/organization/trace_net/evidence_sufficiency_critic \
  --min-sufficiency-records 5 \
  --min-queries 5 \
  --require-hybrid-v2-quality-pass \
  --require-dynamic-final-gate-quality-pass \
  --require-retrieval-critic-quality-pass \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_evidence_sufficiency_critic_v1_quality.py \
  --report-path local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json \
  --min-sufficiency-records 5 \
  --min-queries 5 \
  --require-hybrid-v2-quality-pass \
  --require-dynamic-final-gate-quality-pass \
  --require-retrieval-critic-quality-pass \
  --write-json
```

## Status meanings

```text
final_artifact_evidence_sufficient
  Existing final-gate artifact is safe and clean.

final_evidence_sufficient
  Dynamic final-gate output has safe source/citation/authority-backed final claims.

final_evidence_sufficient_but_retrieval_audit_required
  Dynamic final-gate claims look sufficient, but Retrieval Critic found retrieval consistency risk.

final_gate_claims_need_audit
  Dynamic final gate allowed something but claims/counters need audit.

sufficient_for_final_gate_attempt
  Retrieval groups have source lineage, citation, and authority; run final gate.

insufficient_retrieval_only_evidence
  Retrieval found candidates, but they are not answer-ready.

insufficient_missing_exact_support
  Exact-looking query needs exact hits first.

insufficient_missing_citation
  Candidate groups are missing citations.

unsafe_evidence_blocked
  Unsafe or source-truth-mutation risk appeared; block.
```

## Tests

```bash
python -m pytest \
  tests/unit/test_trace_net_evidence_sufficiency_critic_v1.py \
  tests/unit/test_trace_net_evidence_sufficiency_critic_v1_quality.py \
  tests/unit/test_trace_net_evidence_sufficiency_critic_v1_script_imports.py \
  -q
```
