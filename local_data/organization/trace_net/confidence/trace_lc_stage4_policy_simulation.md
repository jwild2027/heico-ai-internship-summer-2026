# TRACE-Net Layer Confidence Stage 4 Policy Simulation

Status: **OK**
Version: `trace_lc_stage4_policy_simulation_v1`

## Summary
- **records**: 1813
- **pages**: 509
- **policy_version**: trace_lc_confidence_policy_v1
- **policy_layers**: 6
- **policy_rag_include_records**: 932
- **trust_changed_records**: 362
- **rag_action_changed_records**: 179
- **repair_action_changed_records**: 181
- **unsafe_policy_rag_include_records**: 0
- **source_trace_policy_A_records**: 509
- **table_candidate_direct_rag_records**: 0
- **visual_text_above_B_records**: 0

## Current vs policy trust tiers

Current: `{'A': 931, 'B': 286, 'C': 596}`
Policy: `{'A': 901, 'B': 648, 'C': 264}`

## Current vs policy RAG actions

Current: `{'exclude_from_rag': 265, 'exclude_until_table_text_exists': 286, 'exclude_until_table_tiles_exist': 331, 'include_as_derived_context': 60, 'include_as_source_evidence': 509, 'include_as_verified_part_evidence': 362}`
Policy: `{'exclude_from_rag': 86, 'exclude_until_table_text_exists': 286, 'exclude_until_table_tiles_exist': 509, 'include_as_derived_context': 61, 'include_as_source_evidence': 509, 'include_as_verified_part_evidence': 362}`

## Per-layer metrics

| Layer | Records | Current tiers | Policy tiers | Trust changes | RAG changes | Unsafe includes | Avg confidence |
|---|---:|---|---|---:|---:|---:|---:|
| part_catalog | 364 | `{'A': 362, 'C': 2}` | `{'A': 362, 'C': 2}` | 0 | 0 | 0 | 0.871051 |
| source_trace | 509 | `{'A': 509}` | `{'A': 509}` | 0 | 0 | 0 | 0.796367 |
| table_candidate | 509 | `{'C': 509}` | `{'B': 331, 'C': 178}` | 331 | 178 | 0 | 0.747131 |
| table_tile_text_refined | 120 | `{'A': 60, 'C': 60}` | `{'A': 30, 'B': 30, 'C': 60}` | 30 | 0 | 0 | 0.72576 |
| table_tiles | 286 | `{'B': 286}` | `{'B': 286}` | 0 | 0 | 0 | 0.796223 |
| visual_text | 25 | `{'C': 25}` | `{'B': 1, 'C': 24}` | 1 | 1 | 0 | 0.404285 |

## Sample trust changes

- `visual_text:t_p_120_1176_p000001` layer=`visual_text` current=`C` policy=`B` usable=`0.767125` rag=`include_as_derived_context`
- `table_candidate:t_p_120_1176_p000003` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000004` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000005` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000006` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000007` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000008` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000009` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000010` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000011` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000013` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000014` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000015` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000016` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000020` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000021` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000022` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000023` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000026` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000027` layer=`table_candidate` current=`C` policy=`B` usable=`0.7505` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000028` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000029` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000030` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000031` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000032` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000033` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000034` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000036` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000037` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000038` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000039` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000040` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000041` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000042` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000043` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000044` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000045` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000046` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000047` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`
- `table_candidate:t_p_120_1176_p000048` layer=`table_candidate` current=`C` policy=`B` usable=`0.798` rag=`exclude_until_table_tiles_exist`

## Unsafe policy includes

None.

## Recommendation

review_policy_simulation_then_select_low_risk_layers_for_stage5_control
