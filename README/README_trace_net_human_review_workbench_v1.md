# TRACE-Net Human Review Workbench View Model v1

This module builds a read-only reviewer workbench view model from the existing
human review queue and triage artifacts.

It does **not** make review decisions. It prepares UI-ready cards that an IT or
review person can inspect.

## Inputs

- Human Review Triage v1
- Human Review Queue v1
- Callout / Visual Part Verifier v1
- Table Cell Normalizer v1
- Category-Aware Graph UI Overlay v1
- Dublin Core Source Package Extension v1

## Safety contract

Workbench cards are advisory only:

- `can_answer_directly = false`
- `can_prove_claims = false`
- `can_mutate_source_truth = false`
- `source_truth_mutation_allowed = false`
- `raw_feedback_direct_to_llm = false`
- `final_answer_allowed = false`

Human decisions still need the Decision Recorder and Promotion Gate before any
promotion/writeback behavior.

## Run

```bash
python scripts/build_trace_net_human_review_workbench_v1.py \
  --human-review-triage local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json \
  --human-review-queue local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json \
  --callout-visual-part-verifier local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --category-aware-graph-ui-overlay local_data/organization/trace_net/category_aware_graph_ui_overlay/trace_net_category_aware_graph_ui_overlay_v1.json \
  --dublin-core-source-package-extension local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json \
  --output-dir local_data/organization/trace_net/human_review_workbench \
  --require-page-count 509 \
  --min-workbench-cards 1 \
  --min-page-profiles 509 \
  --min-cards-with-page-ids 1 \
  --min-high-priority-cards 1 \
  --min-critical-cards 1 \
  --require-source-triage-quality-pass \
  --require-source-queue-quality-pass \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_human_review_workbench_v1_quality.py \
  --report-path local_data/organization/trace_net/human_review_workbench/trace_net_human_review_workbench_v1.json \
  --require-page-count 509 \
  --min-workbench-cards 1 \
  --min-page-profiles 509 \
  --min-cards-with-page-ids 1 \
  --min-high-priority-cards 1 \
  --min-critical-cards 1 \
  --require-source-triage-quality-pass \
  --require-source-queue-quality-pass \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/human_review_workbench/
  trace_net_human_review_workbench_v1.json
  trace_net_human_review_workbench_v1_cards.jsonl
  trace_net_human_review_workbench_v1_pages.jsonl
  trace_net_human_review_workbench_v1_summary.json
  trace_net_human_review_workbench_v1_quality.json
  trace_net_human_review_workbench_v1_manifest.json
  trace_net_human_review_workbench_v1.md
  trace_net_human_review_workbench_v1.html
```

## Why this matters

The existing queue and triage layers already identify thousands of review tasks
and hundreds of deduplicated triage cards. This module creates a single UI-ready
card per triage item with page/source package, table, visual/callout, category,
and decision hints attached.
