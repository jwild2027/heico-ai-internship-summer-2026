# TRACE-Net Feedback Graph v1

Status: **OK**

## Summary
- **feedback_events**: 3
- **thumbs_up_events**: 1
- **thumbs_down_events**: 2
- **neutral_events**: 0
- **affected_page_count**: 2
- **affected_candidate_count**: 0
- **policy_signal_records**: 2
- **policy_signal_eligible_events**: 1
- **context_valid_events**: 1
- **context_warning_events**: 2
- **query_mismatch_events**: 0
- **affected_page_not_in_answer_events**: 0
- **advisory_only_events**: 3
- **source_truth_mutation_records**: 0

## Recent feedback events

| Created | Rating | Context | Query | Affected pages | Reasons | Comment |
|---|---|---|---|---|---|---|
| 2026-06-03T14:55:40Z | thumbs_down | unknown | `seat bottom backrest` | t_p_120_1176_p000320 | citation_not_supporting_answer, wrong_page | p000003 was the useful evidence for this part. |
| 2026-06-03T14:55:49Z | thumbs_up | unknown | `seat bottom backrest` | t_p_120_1176_p000003 | answer_correct | This page supported the answer. |
| 2026-06-03T15:05:43Z | thumbs_down | valid | `120-50645-009` | t_p_120_1176_p000320 | citation_not_supporting_answer, wrong_page | p000003 was the useful evidence for this part. |

## Advisory policy signals

| Signal | Query fingerprint | Page | Strength | Events | Reasons |
|---|---|---|---:|---:|---|
| boost_for_query | `part_number:120-50645-009` | t_p_120_1176_p000003 | 0.5 | 1 | expected_page:1 |
| demote_for_query | `part_number:120-50645-009` | t_p_120_1176_p000320 | 1.0 | 1 | citation_not_supporting_answer:1, wrong_page:1 |
