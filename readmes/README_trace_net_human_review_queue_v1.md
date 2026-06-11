# TRACE-Net Human Review Queue v1

This module builds a read-only Human Review Queue for TRACE-Net. It turns IT-console issues, fishnet retry signals, table repairs, visual/callout uncertainty, feedback memory, and graph communities into prioritized review tasks.

## Safety contract

Review tasks are advisory only:

- `can_answer_directly = false`
- `can_prove_claims = false`
- `can_mutate_source_truth = false`
- `final_answer_allowed = false`
- `review_queue_authority = human_review_advisory_only`

A review task can ask a person to verify evidence. It cannot make a claim true.

## Build

```bash
python scripts/build_trace_net_human_review_queue_v1.py \
  --it-console local_data/organization/trace_net/it_operations_console/trace_net_it_operations_console_v1.json \
  --fishnet-retry-refined local_data/organization/trace_net/fishnet_retry_refined/trace_net_fishnet_retry_refinement_v1.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --visual-ink-layout-calibrator local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json \
  --callout-visual-part-verifier local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --feedback-memory local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --community-aware-retrieval local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json \
  --final-answer-report local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json \
  --output-dir local_data/organization/trace_net/human_review_queue \
  --min-review-tasks 1 \
  --min-high-priority-review-tasks 1 \
  --require-it-console-quality-pass \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_human_review_queue_v1_quality.py \
  --report-path local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json \
  --min-review-tasks 1 \
  --min-high-priority-review-tasks 1 \
  --require-it-console-quality-pass \
  --write-json
```

## Output

The module writes:

- `trace_net_human_review_queue_v1.json`
- `trace_net_human_review_queue_v1_tasks.jsonl`
- `trace_net_human_review_queue_v1_summary.json`
- `trace_net_human_review_queue_v1_quality.json`
- `trace_net_human_review_queue_v1_manifest.json`
- `trace_net_human_review_queue_v1.md`
- `trace_net_human_review_queue_v1.html`

## Human-readable task types

Example tasks include:

- `review_repaired_table_cells`
- `verify_visual_part_candidates`
- `review_callout_candidates`
- `review_prompt_injection_feedback`
- `review_negative_feedback_target`
- `review_high_signal_graph_community`
- `confirm_blank_source_trace`
- `it_warning_triage`

The queue is intended for backend/admin/reviewer workflows. It is the operational counterpart to the IT Operations Console.
