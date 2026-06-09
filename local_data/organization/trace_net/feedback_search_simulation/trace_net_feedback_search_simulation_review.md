# TRACE-Net Feedback-Aware Search Simulation v1

Status: **OK**  Version: `trace_net_feedback_search_simulation_v1`

## Summary

| Metric | Value |
|---|---|
| query_fingerprint | part_number:120-50645-009 |
| grouped_input_records | 3 |
| simulated_group_records | 3 |
| matching_feedback_signal_records | 2 |
| feedback_signals_used | 2 |
| groups_with_feedback_adjustment | 2 |
| groups_boosted | 1 |
| groups_demoted | 1 |
| rank_changed_records | 2 |
| unsafe_simulated_records | 0 |
| excluded_simulated_records | 0 |
| source_truth_mutation_records | 0 |
| context_warning_signals_used | 0 |
| top_page_before | t_p_120_1176_p000003 |
| top_page_after | t_p_120_1176_p000003 |

## Matching feedback signals

| Signal | Type | Page | Strength | Net | Events | Reasons |
|---|---|---|---|---|---|---|
| feedback_signal:c44938758539 | boost_for_query | t_p_120_1176_p000003 | 0.5 | 0.5 | 1 | {"expected_page": 1} |
| feedback_signal:7de9478188c9 | demote_for_query | t_p_120_1176_p000320 | 1.0 | -1.0 | 1 | {"citation_not_supporting_answer": 1, "wrong_page": 1} |

## Simulated page ranking

| New rank | Old rank | Delta | Page | Base score | Feedback delta | Sim score | Buckets | Signals | Signal types |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 0 | t_p_120_1176_p000003 | 65.581557 | 4.0 | 69.581557 | verified_part_evidence, source_text_evidence, derived_context | 1 | boost_for_query |
| 2 | 3 | 1 | t_p_120_1176_p000319 | 50.251892 | 0.0 | 50.251892 | source_text_evidence | 0 |  |
| 3 | 2 | -1 | t_p_120_1176_p000320 | 61.631557 | -12.0 | 49.631557 | verified_part_evidence, source_text_evidence | 1 | demote_for_query |
