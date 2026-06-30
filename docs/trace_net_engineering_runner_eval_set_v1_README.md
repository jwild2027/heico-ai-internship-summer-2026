# TRACE-Net Engineering Runner Evaluation Set v1

`trace_net_engineering_runner_eval_set_v1` runs the H5 engineering answer runner over a small question set and aggregates PASS/FAIL, citation, source-trace, unsupported-claim, and safety counters.

H6B hardens failure reporting. If a runner stage fails before writing its expected quality-check or stage artifact, the eval set records a structured failure instead of surfacing only a raw `FileNotFoundError`.

Structured failure fields include:

- `failed_stage`
- `failure_type`
- `failure_reason`
- `traceback_tail`

Common failure types:

- `missing_stage_quality_check`
- `missing_stage_artifact`
- `stage_quality_gate_exit`
- `runner_exception`

This module is an evaluation harness only. It does not mutate source-truth artifacts and does not write to Postgres, Qdrant, or OpenSearch.

Default evaluation questions include Figure 69, Figure 75, Figure 91, exact part lookup, nomenclature-debug, and comparison-style prompts. The quality gate can require a minimum number of runner passes while still recording failures for unsupported or not-yet-covered question types.

Safety contract:

- `answer_permission=false`
- `source_truth_mutation_allowed=false`
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads
- no external mutation
