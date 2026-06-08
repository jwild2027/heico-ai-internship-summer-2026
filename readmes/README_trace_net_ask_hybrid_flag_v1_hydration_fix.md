# TRACE-Net Ask Hybrid Flag v1 Hydration Fix

This patch fixes Step 9 when `--retrieval-mode hybrid-simulate` writes a report with zero ranked groups even though Step 7 hybrid retrieval passed.

## Cause

`run_hybrid_retrieval_sim()` returns a compact runtime object that includes paths and summary data. The ranked retrieval groups are written in the full Step 7 report JSON and groups JSONL artifacts. The ask wrapper must hydrate the full Step 7 report before summarizing ask-side groups.

Without hydration, Step 9 can show:

```text
hybrid_quality_status:
ranked_group_count: 0
safe_group_count: 0
Quality status: FAIL
```

## Fix

`tiff/trace_net_ask_hybrid_flag_v1.py` now:

- reads the full Step 7 JSON from `report_path` when available;
- falls back to `groups_path` JSONL if the full report is unavailable;
- accepts both Step 7 shapes: `results` and older `query_results`;
- extracts hybrid quality from `quality.status`, top-level `quality_status`, or `status`;
- preserves the TRACE-Net safety contract: ask hybrid mode remains simulation-only and cannot compose an answer.

## Expected result

After applying this patch, rerunning Step 9 should produce:

```text
TRACE-Net ask hybrid flag v1
 Status: ASK_RAN
 Quality status: PASS
 retrieval_mode: hybrid-simulate
 answer_status: NOT_COMPOSED_SIMULATION_ONLY
 regression_quality_status: PASS
 hybrid_quality_status: PASS
 ranked_group_count: >=1
 safe_group_count: >=1
 unsafe_group_count: 0
 direct_answer_allowed_group_count: 0
 claim_proof_allowed_group_count: 0
 source_truth_mutation_allowed_group_count: 0
```

## Commands

```bash
python -m pytest \
  tests/unit/test_trace_net_ask_hybrid_flag_v1.py \
  tests/unit/test_trace_net_ask_hybrid_flag_v1_quality.py \
  tests/unit/test_trace_net_ask_hybrid_flag_v1_script_imports.py \
  -q
```
