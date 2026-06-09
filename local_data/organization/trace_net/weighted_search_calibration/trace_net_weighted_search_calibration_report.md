# TRACE-Net Weighted Search Calibration Report

Status: **OK**
Version: `trace_net_weighted_search_calibration_v1`

## Summary
- **query_fingerprint**: part_number:120-50645-009
- **weights_policy_version**: trace_net_weights_policy_v1
- **records**: 3
- **pages**: 3
- **feedback_signals_used**: 2
- **groups_with_feedback_adjustment**: 2
- **groups_boosted**: 1
- **groups_demoted**: 1
- **rank_changed_records**: 0
- **feedback_cap_hit_records**: 1
- **demotion_shortfall_records**: 1
- **evidence_diversity_overrode_feedback_records**: 1
- **unsafe_records**: 0
- **excluded_records**: 0
- **source_truth_mutation_records**: 0
- **context_warning_signals_used**: 0
- **top_page_before**: t_p_120_1176_p000003
- **top_page_after**: t_p_120_1176_p000003

## Component statistics
| Component | Average | Min | Max | Nonzero records |
|---|---|---|---|---|
| base_score | 50.505002 | 46.351892 | 52.581557 | 3 |
| bucket_bonus | 11.333333 | 5.0 | 16.0 | 3 |
| evidence_diversity_bonus | 4.0 | 0.0 | 8.0 | 2 |
| exact_match_bonus | 22.0 | 22.0 | 22.0 | 3 |
| confidence_bonus | 2.5175 | 2.29425 | 2.643375 | 3 |
| feedback_adjustment | -3.0 | -15.0 | 6.0 | 2 |

## Ranking records
| Weighted rank | Original rank | Page | Score | Feedback | Buckets | Margin next | Demotion needed | Reasons |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | t_p_120_1176_p000003 | 107.224932 | 6.0 | verified_part_evidence, source_text_evidence, derived_context | 28.0285 | 28.028501 | validated_feedback_boost, verified_part_evidence_present, source_text_evidence_present, derived_context_present, multiple_evidence_buckets |
| 2 | 2 | t_p_120_1176_p000320 | 79.196432 | -15.0 | verified_part_evidence, source_text_evidence | 3.55029 | 3.550291 | validated_feedback_demote, feedback_cap_hit, verified_part_evidence_present, source_text_evidence_present, multiple_evidence_buckets, demoted_but_rank_preserved, additional_demotion_required_for_next_rank |
| 3 | 3 | t_p_120_1176_p000319 | 75.646142 | 0.0 | source_text_evidence | None | None | source_text_evidence_present |

## Feedback cap hit records
| Page | Feedback | Lower page | Additional demotion needed | Buckets |
|---|---|---|---|---|
| t_p_120_1176_p000320 | -15.0 | t_p_120_1176_p000319 | 3.550291 | verified_part_evidence, source_text_evidence |

## Recommendations
- `weighted_simulation_kept_unsafe_results_out`
- `context_warning_feedback_ignored_for_ranking`
- `feedback_adjusted_scores_without_rank_change_review_margins_before_tuning`
- `feedback_cap_hit_review_repeated_or_expert_feedback_before_increasing_penalty`
- `evidence_diversity_preserved_rank_despite_negative_feedback`
- `do_not_apply_weighted_ranking_until_regression_queries_pass`
