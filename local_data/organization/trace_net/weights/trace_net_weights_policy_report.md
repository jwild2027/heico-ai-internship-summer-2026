# TRACE-Net Weights Policy v1

Status: **OK**
Version: `trace_net_weights_policy_v1`

## Purpose

This policy stores the first official TRACE-Net weight recommendations for confidence scoring, retrieval ranking, and validated feedback adjustments.

It is **configuration only**. It does not change production ranking or source truth by itself.

## Confidence layer weights

| Layer | Source | Graph | OCR | Catalog | Extraction | A | B | C | Max tier | RAG action |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| source_trace | 0.70 | 0.20 | 0.05 | 0.00 | 0.05 | 0.75 | 0.6 | 0.4 | A | include_as_source_evidence |
| source_text_evidence | 0.30 | 0.20 | 0.40 | 0.05 | 0.05 | 0.8 | 0.65 | 0.45 | A | include_as_source_text_evidence |
| part_catalog | 0.25 | 0.20 | 0.10 | 0.40 | 0.05 | 0.82 | 0.66 | 0.42 | A | include_as_verified_part_evidence |
| table_tile_text_refined | 0.25 | 0.20 | 0.10 | 0.35 | 0.10 | 0.82 | 0.64 | 0.4 | A | include_as_derived_context |
| visual_text | 0.25 | 0.30 | 0.20 | 0.10 | 0.15 | 0.92 | 0.74 | 0.45 | B | include_as_derived_context |
| table_candidate | 0.15 | 0.40 | 0.05 | 0.00 | 0.40 | 0.9 | 0.66 | 0.4 | B | exclude_until_table_tiles_exist |
| table_tiles | 0.25 | 0.25 | 0.00 | 0.00 | 0.50 | 0.9 | 0.65 | 0.4 | B | exclude_until_table_text_exists |

## Retrieval ranking weights

Bucket bonuses:
- `derived_context`: +3.0
- `source_evidence`: +2.0
- `source_text_evidence`: +5.0
- `verified_part_evidence`: +8.0

Exact-match bonuses:
- `all_query_terms_matched`: +10.0
- `exact_page_id_match`: +25.0
- `exact_part_number_match`: +20.0
- `exact_phrase_match`: +8.0
- `per_matched_term`: +2.0

## Feedback ranking weights

- `answer_correct`: +6
- `answer_too_vague`: -3
- `citation_not_supporting_answer`: -7
- `citation_useful`: +4
- `expected_page_boost`: +8
- `source_helpful`: +5
- `wrong_page`: -8
- `wrong_part`: -10
- feedback cap: `-15.0` to `15.0`

## Risk scores

- `catalog_conflict`: 0.8
- `context_warning_feedback`: 0.6
- `graph_conflict`: 0.7
- `hallucination_risk_high`: 0.7
- `hallucination_risk_low`: 0.4
- `low_risk`: 0.05
- `metadata_leakage`: 1.0
- `noisy_ocr_or_tile_text`: 0.3
- `prompt_template_leakage`: 1.0
- `refusal_like`: 0.95
- `source_untraceable`: 1.0
- `unsupported_specific_claim`: 0.5

## Global safety gates

- `source_untraceable_records_must_not_enter_rag`
- `metadata_leakage_records_must_not_enter_rag`
- `prompt_template_leakage_records_must_not_enter_rag`
- `refusal_like_records_must_not_enter_rag`
- `D_tier_records_must_not_enter_rag`
- `routing_only_layers_must_not_enter_rag_directly`
- `feedback_must_not_mutate_source_truth`
- `context_warning_feedback_must_not_adjust_ranking`

## Validation checks

- OK version: trace_net_weights_policy_v1
- OK required_layers: 7 present
- OK weights[part_catalog]: sum=1.0
- OK thresholds[part_catalog]: A=0.82 B=0.66 C=0.42
- OK weights[source_text_evidence]: sum=1.0
- OK thresholds[source_text_evidence]: A=0.8 B=0.65 C=0.45
- OK weights[source_trace]: sum=1.0
- OK thresholds[source_trace]: A=0.75 B=0.6 C=0.4
- OK weights[table_candidate]: sum=1.0
- OK thresholds[table_candidate]: A=0.9 B=0.66 C=0.4
- OK weights[table_tile_text_refined]: sum=1.0
- OK thresholds[table_tile_text_refined]: A=0.82 B=0.64 C=0.4
- OK weights[table_tiles]: sum=1.0
- OK thresholds[table_tiles]: A=0.9 B=0.65 C=0.4
- OK weights[visual_text]: sum=1.0
- OK thresholds[visual_text]: A=0.92 B=0.74 C=0.45
- OK source_trace_policy: max=A and source evidence action
- OK source_text_policy: OCR-weighted source text evidence present
- OK visual_text_policy: conservative max=B and prompt leakage hard block
- OK table_candidate_policy: routing/preprocessing only, no direct RAG
- OK table_tiles_policy: routing/preprocessing only, no direct RAG
- OK table_tile_text_policy: B+ routes as derived context
- OK risk_scores: count=12
- OK risk_combination: max
- OK retrieval_bucket_bonuses: required buckets present
- OK feedback_reason_weights: positive and negative signs sane
- OK feedback_caps: -15.0..15.0
- OK feedback_context_validation: valid-only and warning ignored
- OK global_safety_gates: count=8
- OK rollout: config only, no production ranking/source truth mutation

## Metrics

- **error_count**: `0`
- **feedback_reason_count**: `8`
- **global_safety_gate_count**: `8`
- **layer_count**: `7`
- **missing_layers**: `[]`
- **retrieval_bucket_bonus_count**: `4`
- **risk_score_count**: `12`
- **weight_sums**: `{'part_catalog': 1.0, 'source_text_evidence': 1.0, 'source_trace': 1.0, 'table_candidate': 1.0, 'table_tile_text_refined': 1.0, 'table_tiles': 1.0, 'visual_text': 1.0}`
