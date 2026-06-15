# TRACE-Net Regression Evaluation v1

Step 8 compares the Step 7 hybrid retrieval simulation against a small regression set before hybrid retrieval is allowed near `ask`.

This is a read-only gate. It does not call an LLM, does not mutate Postgres, does not mutate Qdrant, and does not treat retrieval results as answers.

## Inputs

Default hybrid report:

```text
local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json
```

Optional custom regression set:

```bash
--regression-set path/to/regression_set.json
```

If no regression set is provided, the script uses the built-in five-case Step 7 set:

```text
manual_revision_history
ata_25_21_placards
part_nomenclature_lookup
source_trace_page_000001
technical_publication_evidence
```

## Outputs

```text
local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1.json
local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1_cases.jsonl
local_data/organization/trace_net/regression_eval/trace_net_regression_set_v1.json
local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1_summary.json
local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1_manifest.json
local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1_quality.json
```

## Run

```bash
python scripts/run_trace_net_regression_eval_v1.py \
  --hybrid-report local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json \
  --output-dir local_data/organization/trace_net/regression_eval \
  --min-regression-cases 5 \
  --min-cases-with-results 5 \
  --min-cases-with-candidate-hits 5 \
  --min-cases-with-page-profile-hits 5 \
  --min-total-ranked-groups 25 \
  --min-total-candidate-hits 25 \
  --min-total-page-profile-hits 25 \
  --require-all-cases-pass \
  --require-hybrid-quality-pass \
  --require-candidate-count 1476 \
  --require-page-profile-count 509 \
  --require-embedding-dim 1024 \
  --quality
```

## Check quality

```bash
python scripts/check_trace_net_regression_eval_v1_quality.py \
  --report-path local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1.json \
  --min-regression-cases 5 \
  --min-cases-with-results 5 \
  --min-cases-with-candidate-hits 5 \
  --min-cases-with-page-profile-hits 5 \
  --min-total-ranked-groups 25 \
  --min-total-candidate-hits 25 \
  --min-total-page-profile-hits 25 \
  --require-all-cases-pass \
  --require-hybrid-quality-pass \
  --require-candidate-count 1476 \
  --require-page-profile-count 509 \
  --require-embedding-dim 1024 \
  --write-json
```

Expected result:

```text
TRACE-Net regression evaluation v1
 Status: PASS
 Quality status: PASS
 case_fail_count: 0
 required_case_missing_count: 0
 case_unsafe_result_count: 0
 case_direct_answer_allowed_count: 0
 case_claim_proof_allowed_count: 0
 case_source_truth_mutation_allowed_count: 0
```

## TRACE-Net safety contract

This step keeps the same boundary:

```text
Hybrid retrieval can rank and group.
Hybrid retrieval cannot answer.
Hybrid retrieval cannot prove claims by itself.
Hybrid retrieval cannot mutate source truth.
Only source/citation/trust-authorized evidence can support answers later.
```
