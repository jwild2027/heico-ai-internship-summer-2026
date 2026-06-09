# TRACE-Net Fixed Regression Report v1

Status: **OK**
Version: `trace_net_regression_report_v1`

## Summary
- **case_records**: 7
- **passed_cases**: 7
- **failed_cases**: 0
- **review_needed_cases**: 2
- **top_page_changed_cases**: 1
- **tie_heavy_cases**: 1
- **feedback_signal_cases**: 1
- **rank_changed_cases**: 1
- **unsafe_answer_group_total**: 0
- **unsafe_weighted_record_total**: 0
- **excluded_weighted_record_total**: 0
- **source_truth_mutation_total**: 0
- **context_warning_signals_used_total**: 0
- **answer_page_total**: 41
- **answer_evidence_total**: 61

## Recommendations
- `fixed_regression_set_safe_for_current_outputs`
- `review_weighted_top_page_changes_before_applying_weighted_ranking`
- `review_tie_heavy_queries_for_additional_tie_breakers`
- `validated_feedback_path_exercised_in_regression_set`
- `do_not_apply_weighted_ranking_without_regression_review`

## Case table
| Case | Query | Ask | Pages | Evidence | Unsafe answer | Weighted top before | Weighted top after | Flags |
|---|---|---:|---:|---:|---:|---|---|---|
| effective_pages | effective pages | OK | 7 | 10 | 0 | t_p_120_1176_p000005 | t_p_120_1176_p000005 |  |
| numerical_index | numerical index | OK | 4 | 10 | 0 | t_p_120_1176_p000005 | t_p_120_1176_p000005 |  |
| page_p000010 | t_p_120_1176_p000010 | OK | 1 | 5 | 0 | t_p_120_1176_p000010 | t_p_120_1176_p000010 |  |
| part_120_50645_009 | 120-50645-009 | OK | 3 | 8 | 0 | t_p_120_1176_p000003 | t_p_120_1176_p000003 | `feedback_signals_used` |
| passenger_seat | passenger seat | OK | 10 | 10 | 0 | t_p_120_1176_p000082 | t_p_120_1176_p000082 | `tie_heavy_top_scores` |
| seat_bottom_backrest | seat bottom backrest | OK | 10 | 10 | 0 | t_p_120_1176_p000015 | t_p_120_1176_p000015 |  |
| vendor_list | vendor list | OK | 6 | 8 | 0 | t_p_120_1176_p000021 | t_p_120_1176_p000005 | `weighted_top_page_changed`, `weighted_rank_changes` |

## Weighted top-page changes
- `vendor_list`: `t_p_120_1176_p000021` -> `t_p_120_1176_p000005`

## Tie-heavy cases
- `passenger_seat`: top_score_tie_count=10 score_spread=0.0

## Safety
The report is read-only. It does not change production ranking, source truth, Evidence Consensus, RAG eligibility, or feedback records.
