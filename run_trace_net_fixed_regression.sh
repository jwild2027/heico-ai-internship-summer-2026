#!/usr/bin/env bash
set -euo pipefail

REG_DIR="local_data/organization/trace_net/regression/fixed_set_v1"
mkdir -p "$REG_DIR"

run_case() {
  local case_id="$1"
  shift

  local case_dir="$REG_DIR/$case_id"
  mkdir -p "$case_dir"

  echo ""
  echo "============================================================"
  echo "Running regression case: $case_id"
  echo "Command args: $*"
  echo "============================================================"

  python legacy/scripts/obsolete_cli/trace_net_ask.py "$@" --top-k 10

  python scripts/maintenance/benchmark/check_trace_net_ask_quality.py \
    --write-json \
    --min-answer-pages 1 \
    --min-evidence-records 1 \
    --max-unsafe-answer-groups 0 \
    --require-feedback-mode off

  python scripts/operations/ingestion/simulate_trace_net_weighted_search.py

  python scripts/maintenance/benchmark/check_trace_net_weighted_search_quality.py \
    --write-json \
    --min-groups 1 \
    --min-pages 1 \
    --min-rank-comparison-records 1 \
    --max-unsafe-results 0 \
    --max-excluded-results 0 \
    --max-source-truth-mutations 0 \
    --max-context-warning-signals-used 0

  cp -f local_data/organization/trace_net/ask/trace_net_ask_summary.json "$case_dir/ask_summary.json"
  cp -f local_data/organization/trace_net/ask/trace_net_ask_quality.json "$case_dir/ask_quality.json" 2>/dev/null || true
  cp -f local_data/organization/trace_net/ask/trace_net_ask_report.md "$case_dir/ask_report.md"
  cp -f local_data/organization/trace_net/ask/trace_net_ask_report.html "$case_dir/ask_report.html"

  cp -f local_data/organization/trace_net/search/trace_net_search_summary.json "$case_dir/search_summary.json"
  cp -f local_data/organization/trace_net/search/trace_net_search_results.jsonl "$case_dir/search_results.jsonl"
  cp -f local_data/organization/trace_net/search/trace_net_search_grouped_summary.json "$case_dir/grouped_summary.json"
  cp -f local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl "$case_dir/grouped_results.jsonl"
  cp -f local_data/organization/trace_net/search/trace_net_search_grouped_review.html "$case_dir/grouped_review.html"

  cp -f local_data/organization/trace_net/answers/trace_net_answer_summary.json "$case_dir/answer_summary.json"
  cp -f local_data/organization/trace_net/answers/trace_net_answer_draft.md "$case_dir/answer.md"
  cp -f local_data/organization/trace_net/answers/trace_net_answer_draft.html "$case_dir/answer.html"
  cp -f local_data/organization/trace_net/answers/trace_net_answer_quality.json "$case_dir/answer_quality.json" 2>/dev/null || true

  cp -f local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_summary.json "$case_dir/weighted_search_summary.json"
  cp -f local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_results.jsonl "$case_dir/weighted_search_results.jsonl"
  cp -f local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_quality.json "$case_dir/weighted_search_quality.json" 2>/dev/null || true
  cp -f local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_review.html "$case_dir/weighted_search_review.html"

  echo "Saved case artifacts to: $case_dir"
}

run_case "part_120_50645_009" --part-number "120-50645-009"
run_case "seat_bottom_backrest" --query "seat bottom backrest"
run_case "page_p000010" --page-id "t_p_120_1176_p000010"
run_case "numerical_index" --query "numerical index"
run_case "effective_pages" --query "effective pages"
run_case "vendor_list" --query "vendor list"
run_case "passenger_seat" --query "passenger seat"

echo ""
echo "============================================================"
echo "Fixed regression set complete"
echo "Artifacts: $REG_DIR"
echo "============================================================"
