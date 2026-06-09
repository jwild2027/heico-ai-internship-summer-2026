# TRACE-Net Layer Confidence Stage 2 Evaluation

Status: **OK**
Version: `trace_lc_stage2_eval_v1`

## Summary
- **records**: 1813
- **scored_records**: 1813
- **missing_confidence_records**: 0
- **agreement_rate**: 0.239382
- **disagreement_records**: 1379
- **within_one_tier_rate**: 0.986762
- **confidence_higher_records**: 424
- **confidence_lower_records**: 955
- **rule_includes_confidence_low_records**: 24
- **rule_excludes_confidence_high_records**: 710
- **blocked_high_confidence_records**: 0
- **source_trace_confidence_below_A_records**: 509
- **avg_usable_confidence**: 0.787436
- **avg_support_score**: 0.83376
- **avg_risk_score**: 0.055957

Recommendation: `calibrate_layer_specific_thresholds_before_using_scores_for_routing`

## Confusion Matrix

Rows are current rule-based trust tiers. Columns are TRACE-LC confidence tiers.

| Current \ Confidence | A | B | C | D |
|---|---:|---:|---:|---:|
| A | 0 | 907 | 24 | 0 |
| B | 0 | 286 | 0 | 0 |
| C | 0 | 424 | 148 | 24 |
| D | 0 | 0 | 0 | 0 |

## Per-layer metrics

| Layer | Records | Agreement | Current tiers | Confidence tiers | Avg usable | Avg risk |
|---|---:|---:|---|---|---:|---:|
| part_catalog | 364 | 0.0 | `{'A': 362, 'C': 2}` | `{'B': 364}` | 0.871051 | 0.05 |
| source_trace | 509 | 0.0 | `{'A': 509}` | `{'B': 495, 'C': 14}` | 0.796367 | 0.05 |
| table_candidate | 509 | 0.180747 | `{'C': 509}` | `{'B': 417, 'C': 92}` | 0.747131 | 0.05 |
| table_tile_text_refined | 120 | 0.466667 | `{'A': 60, 'C': 60}` | `{'B': 54, 'C': 66}` | 0.72576 | 0.05 |
| table_tiles | 286 | 1.0 | `{'B': 286}` | `{'B': 286}` | 0.796223 | 0.05 |
| visual_text | 25 | 0.0 | `{'C': 25}` | `{'B': 1, 'D': 24}` | 0.404285 | 0.482 |

## Promotion candidate samples

- `t_p_120_1176_p000078:part_catalog` page=`t_p_120_1176_p000078` layer=`part_catalog` trust=`C` confidence=`B` usable=`0.767125` action=`exclude_from_rag`
- `t_p_120_1176_p000491:part_catalog` page=`t_p_120_1176_p000491` layer=`part_catalog` trust=`C` confidence=`B` usable=`0.767125` action=`exclude_from_rag`
- `t_p_120_1176_p000001:visual_text` page=`t_p_120_1176_p000001` layer=`visual_text` trust=`C` confidence=`B` usable=`0.767125` action=`exclude_from_rag`
- `t_p_120_1176_p000001:table_candidate` page=`t_p_120_1176_p000001` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.703` action=`exclude_from_rag`
- `t_p_120_1176_p000003:table_candidate` page=`t_p_120_1176_p000003` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.798` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000004:table_candidate` page=`t_p_120_1176_p000004` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000005:table_candidate` page=`t_p_120_1176_p000005` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.798` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000006:table_candidate` page=`t_p_120_1176_p000006` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.798` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000007:table_candidate` page=`t_p_120_1176_p000007` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.798` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000008:table_candidate` page=`t_p_120_1176_p000008` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.798` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000009:table_candidate` page=`t_p_120_1176_p000009` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.798` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000010:table_candidate` page=`t_p_120_1176_p000010` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.798` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000011:table_candidate` page=`t_p_120_1176_p000011` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000013:table_candidate` page=`t_p_120_1176_p000013` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000014:table_candidate` page=`t_p_120_1176_p000014` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000015:table_candidate` page=`t_p_120_1176_p000015` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000016:table_candidate` page=`t_p_120_1176_p000016` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000017:table_candidate` page=`t_p_120_1176_p000017` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.703` action=`exclude_from_rag`
- `t_p_120_1176_p000020:table_candidate` page=`t_p_120_1176_p000020` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000021:table_candidate` page=`t_p_120_1176_p000021` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000022:table_candidate` page=`t_p_120_1176_p000022` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000023:table_candidate` page=`t_p_120_1176_p000023` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000024:table_candidate` page=`t_p_120_1176_p000024` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.703` action=`exclude_from_rag`
- `t_p_120_1176_p000026:table_candidate` page=`t_p_120_1176_p000026` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`
- `t_p_120_1176_p000027:table_candidate` page=`t_p_120_1176_p000027` layer=`table_candidate` trust=`C` confidence=`B` usable=`0.7505` action=`exclude_until_table_tiles_exist`

## Demotion candidate samples

- `t_p_120_1176_p000002:source_trace` page=`t_p_120_1176_p000002` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000012:source_trace` page=`t_p_120_1176_p000012` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000025:source_trace` page=`t_p_120_1176_p000025` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000035:source_trace` page=`t_p_120_1176_p000035` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000079:source_trace` page=`t_p_120_1176_p000079` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000091:source_trace` page=`t_p_120_1176_p000091` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000103:source_trace` page=`t_p_120_1176_p000103` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000111:source_trace` page=`t_p_120_1176_p000111` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000121:source_trace` page=`t_p_120_1176_p000121` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000187:source_trace` page=`t_p_120_1176_p000187` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000195:source_trace` page=`t_p_120_1176_p000195` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000201:source_trace` page=`t_p_120_1176_p000201` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000217:source_trace` page=`t_p_120_1176_p000217` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000335:source_trace` page=`t_p_120_1176_p000335` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000007:table_tile_text_refined` page=`t_p_120_1176_p000007` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000008:table_tile_text_refined` page=`t_p_120_1176_p000008` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000008:table_tile_text_refined` page=`t_p_120_1176_p000008` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000009:table_tile_text_refined` page=`t_p_120_1176_p000009` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000010:table_tile_text_refined` page=`t_p_120_1176_p000010` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000028:table_tile_text_refined` page=`t_p_120_1176_p000028` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000030:table_tile_text_refined` page=`t_p_120_1176_p000030` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000032:table_tile_text_refined` page=`t_p_120_1176_p000032` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000036:table_tile_text_refined` page=`t_p_120_1176_p000036` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`
- `t_p_120_1176_p000037:table_tile_text_refined` page=`t_p_120_1176_p000037` layer=`table_tile_text_refined` trust=`A` confidence=`C` usable=`0.64125` action=`include_as_derived_context`

## Blocked high-confidence samples

None.

## Largest disagreement samples

- `t_p_120_1176_p000001:source_trace` page=`t_p_120_1176_p000001` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000002:source_trace` page=`t_p_120_1176_p000002` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000003:source_trace` page=`t_p_120_1176_p000003` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000004:source_trace` page=`t_p_120_1176_p000004` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000005:source_trace` page=`t_p_120_1176_p000005` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000006:source_trace` page=`t_p_120_1176_p000006` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000007:source_trace` page=`t_p_120_1176_p000007` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000008:source_trace` page=`t_p_120_1176_p000008` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000009:source_trace` page=`t_p_120_1176_p000009` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000010:source_trace` page=`t_p_120_1176_p000010` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000011:source_trace` page=`t_p_120_1176_p000011` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000012:source_trace` page=`t_p_120_1176_p000012` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`
- `t_p_120_1176_p000013:source_trace` page=`t_p_120_1176_p000013` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000014:source_trace` page=`t_p_120_1176_p000014` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000015:source_trace` page=`t_p_120_1176_p000015` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000016:source_trace` page=`t_p_120_1176_p000016` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000017:source_trace` page=`t_p_120_1176_p000017` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000018:source_trace` page=`t_p_120_1176_p000018` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000019:source_trace` page=`t_p_120_1176_p000019` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000020:source_trace` page=`t_p_120_1176_p000020` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000021:source_trace` page=`t_p_120_1176_p000021` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000022:source_trace` page=`t_p_120_1176_p000022` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000023:source_trace` page=`t_p_120_1176_p000023` layer=`source_trace` trust=`A` confidence=`B` usable=`0.76475` action=`include_as_source_evidence`
- `t_p_120_1176_p000024:source_trace` page=`t_p_120_1176_p000024` layer=`source_trace` trust=`A` confidence=`B` usable=`0.81225` action=`include_as_source_evidence`
- `t_p_120_1176_p000025:source_trace` page=`t_p_120_1176_p000025` layer=`source_trace` trust=`A` confidence=`C` usable=`0.67925` action=`include_as_source_evidence`

