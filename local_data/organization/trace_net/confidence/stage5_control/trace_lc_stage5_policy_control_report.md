# TRACE-Net Layer Confidence Stage 5b Policy Control

Status: **OK**
Version: `trace_lc_stage5b_policy_control_v1`

## Summary
- **records**: 1813
- **pages**: 509
- **policy_version**: trace_lc_confidence_policy_v1
- **controlled_layers**: ['part_catalog', 'source_trace', 'table_tile_text_refined']
- **policy_controlled_records**: 993
- **rule_controlled_records**: 820
- **stage5_rag_include_records**: 931
- **trust_changed_records**: 30
- **rag_action_changed_records**: 0
- **repair_action_changed_records**: 2
- **unsafe_stage5_rag_include_records**: 0
- **source_trace_policy_A_records**: 509
- **part_catalog_policy_A_records**: 362
- **table_candidate_direct_rag_records**: 0
- **table_tiles_direct_rag_records**: 0
- **visual_text_controlled_records**: 0
- **table_tile_text_refined_controlled_records**: 120
- **table_tile_text_refined_derived_context_records**: 60
- **table_tile_text_refined_direct_verified_records**: 0
- **recommendation**: stage5b_safe_for_downstream_controlled_decision_view

## Selected trust tiers

`{'A': 901, 'B': 316, 'C': 596}`

## Selected RAG actions

`{'exclude_from_rag': 265, 'exclude_until_table_text_exists': 286, 'exclude_until_table_tiles_exist': 331, 'include_as_derived_context': 60, 'include_as_source_evidence': 509, 'include_as_verified_part_evidence': 362}`

## Per-layer metrics

| Layer | Records | Controlled | Selected tiers | Selected RAG actions | Unsafe includes | Avg confidence |
|---|---:|---:|---|---|---:|---:|
| part_catalog | 364 | 364 | `{'A': 362, 'C': 2}` | `{'exclude_from_rag': 2, 'include_as_verified_part_evidence': 362}` | 0 | 0.871051 |
| source_trace | 509 | 509 | `{'A': 509}` | `{'include_as_source_evidence': 509}` | 0 | 0.796367 |
| table_candidate | 509 | 0 | `{'C': 509}` | `{'exclude_from_rag': 178, 'exclude_until_table_tiles_exist': 331}` | 0 | 0.747131 |
| table_tile_text_refined | 120 | 120 | `{'A': 30, 'B': 30, 'C': 60}` | `{'exclude_from_rag': 60, 'include_as_derived_context': 60}` | 0 | 0.72576 |
| table_tiles | 286 | 0 | `{'B': 286}` | `{'exclude_until_table_text_exists': 286}` | 0 | 0.796223 |
| visual_text | 25 | 0 | `{'C': 25}` | `{'exclude_from_rag': 25}` | 0 | 0.404285 |

## Controlled change samples
- `table_tile_text_refined:t_p_120_1176_p000005:tile_t_p_120_1176_p000005_tile_001` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000005:tile_t_p_120_1176_p000005_tile_002` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000005:tile_t_p_120_1176_p000005_tile_003` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000006:tile_t_p_120_1176_p000006_tile_002` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000006:tile_t_p_120_1176_p000006_tile_003` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000006:tile_t_p_120_1176_p000006_tile_004` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000007:tile_t_p_120_1176_p000007_tile_001` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000007:tile_t_p_120_1176_p000007_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000008:tile_t_p_120_1176_p000008_tile_001` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000008:tile_t_p_120_1176_p000008_tile_002` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000008:tile_t_p_120_1176_p000008_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000009:tile_t_p_120_1176_p000009_tile_001` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000009:tile_t_p_120_1176_p000009_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000010:tile_t_p_120_1176_p000010_tile_002` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000010:tile_t_p_120_1176_p000010_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000028:tile_t_p_120_1176_p000028_tile_003` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000028:tile_t_p_120_1176_p000028_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000029:tile_t_p_120_1176_p000029_tile_004` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000029:tile_t_p_120_1176_p000029_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000029:tile_t_p_120_1176_p000029_tile_006` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000030:tile_t_p_120_1176_p000030_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000031:tile_t_p_120_1176_p000031_tile_006` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000032:tile_t_p_120_1176_p000032_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000033:tile_t_p_120_1176_p000033_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000033:tile_t_p_120_1176_p000033_tile_006` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000036:tile_t_p_120_1176_p000036_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000037:tile_t_p_120_1176_p000037_tile_001` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000037:tile_t_p_120_1176_p000037_tile_002` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000037:tile_t_p_120_1176_p000037_tile_005` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `table_tile_text_refined:t_p_120_1176_p000037:tile_t_p_120_1176_p000037_tile_006` layer=`table_tile_text_refined` current=`A` selected=`B` rag=`include_as_derived_context`
- `part_catalog:t_p_120_1176_p000078` layer=`part_catalog` current=`C` selected=`C` rag=`exclude_from_rag`
- `part_catalog:t_p_120_1176_p000491` layer=`part_catalog` current=`C` selected=`C` rag=`exclude_from_rag`

## Unsafe include samples
None.
