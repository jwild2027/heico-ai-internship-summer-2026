# TRACE-Net Ask Final Gate Flag v1

Step 13 exposes a passed Step 12 final-answer gate artifact through an ask-facing command, but only behind an explicit answer flag:

```bash
--answer-mode final-gate
```

This stage does not run retrieval, mutate source truth, mutate trust, or allow free-form LLM answers. It reads the Step 12 final-answer gate report, verifies that the final gate passed, and writes ask-style artifacts only when every final claim is citation-backed, authority-bearing, leak-free, and non-retrieval-only.

## Inputs

Default input:

```text
local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json
```

Expected upstream status:

```text
quality_status = PASS
answer_status = FINAL_ANSWER_GATE_APPROVED
final_answer_allowed = true
uncited_final_claim_count = 0
retrieval_only_final_claim_count = 0
local_path_leak_count = 0
raw_bytes_repr_count = 0
boilerplate_leak_count = 0
source_truth_mutation_allowed_count = 0
```

## Outputs

Default output directory:

```text
local_data/organization/trace_net/ask_final_gate/
```

Generated files:

```text
trace_net_ask_final_gate_v1.json
trace_net_ask_final_gate_v1_claims.jsonl
trace_net_ask_final_gate_v1_summary.json
trace_net_ask_final_gate_v1_manifest.json
trace_net_ask_final_gate_v1_quality.json
trace_net_ask_final_gate_v1_answer.md
trace_net_ask_final_gate_v1_answer.html
```

Do not commit generated `local_data/...` artifacts.

## Run

```bash
python scripts/run_trace_net_ask_final_gate_v1.py \
  --query "Which pages discuss manual revision history?" \
  --retrieval-mode hybrid-simulate \
  --answer-mode final-gate \
  --final-answer-report local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json \
  --min-final-claims 1 \
  --require-answer-mode final-gate \
  --require-retrieval-mode hybrid-simulate \
  --require-final-answer-gate-pass \
  --require-final-answer-allowed \
  --require-embedding-dim 1024 \
  --quality
```

Expected shape:

```text
TRACE-Net ask final gate v1
 Status: ASK_FINAL_GATE_RAN
 Quality status: PASS
 retrieval_mode: hybrid-simulate
 answer_mode: final-gate
 answer_status: FINAL_ANSWER_DELIVERED_BY_GATE
 ask_final_answer_allowed: True
 final_answer_gate_quality_status: PASS
 final_answer_gate_answer_status: FINAL_ANSWER_GATE_APPROVED
 final_claim_count: >=1
 uncited_final_claim_count: 0
 retrieval_only_final_claim_count: 0
 local_path_leak_count: 0
 raw_bytes_repr_count: 0
 boilerplate_leak_count: 0
 source_truth_mutation_allowed_count: 0
```

## Quality check

```bash
python scripts/check_trace_net_ask_final_gate_v1_quality.py \
  --report-path local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1.json \
  --min-final-claims 1 \
  --require-answer-mode final-gate \
  --require-retrieval-mode hybrid-simulate \
  --require-final-answer-gate-pass \
  --require-final-answer-allowed \
  --require-embedding-dim 1024 \
  --write-json
```

## Safety contract

Allowed into ask final-gate output:

```text
Step 12 final-answer text
Step 12 final claims
citation IDs
page IDs
source_text_evidence / verified_part_evidence claims only
```

Blocked:

```text
answer mode off
uncited final claims
retrieval-only claims
page_retrieval_profile proof
context_retrieval_helper proof
source_evidence locator proof
local paths
raw byte wrappers
TRACE-Net boilerplate leaks
source truth mutation
LLM free-form answer claims
```

The default ask path remains unchanged. This stage only exposes a final answer when `--answer-mode final-gate` is explicitly requested and the Step 12 gate has already approved the answer.
