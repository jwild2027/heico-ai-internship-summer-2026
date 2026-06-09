# TRACE-Net RAG Eligibility v1

Status: **OK**
Version: `trace_net_rag_eligibility_v1`

## Summary
- **records**: 1813
- **pages**: 509
- **rag_eligible_records**: 931
- **rag_excluded_records**: 882
- **source_evidence_records**: 509
- **verified_part_evidence_records**: 362
- **derived_context_records**: 60
- **unsafe_rag_eligible_records**: 0
- **stage5_controlled_records**: 993
- **graph_nodes**: 2348
- **graph_edges**: 10882

## RAG buckets
`{'derived_context': 60, 'excluded': 882, 'source_evidence': 509, 'verified_part_evidence': 362}`

## RAG actions
`{'exclude_from_rag': 265, 'exclude_until_table_text_exists': 286, 'exclude_until_table_tiles_exist': 331, 'include_as_derived_context': 60, 'include_as_source_evidence': 509, 'include_as_verified_part_evidence': 362}`

## Trust tiers
`{'A': 901, 'B': 316, 'C': 596}`

## Source evidence samples
| Page | Layer | Trust | RAG action | Confidence | Reasons |
|---|---|---|---|---|---|
| t_p_120_1176_p000001 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000002 | source_trace | A | include_as_source_evidence | 0.67925 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000003 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000004 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000005 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000006 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000007 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000008 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000009 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000010 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000011 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000012 | source_trace | A | include_as_source_evidence | 0.67925 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000013 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000014 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000015 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000016 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000017 | source_trace | A | include_as_source_evidence | 0.81225 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000018 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000019 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |
| t_p_120_1176_p000020 | source_trace | A | include_as_source_evidence | 0.76475 | source_trace_or_source_evidence_selected; safe_for_source_index |

## Verified part evidence samples
| Page | Layer | Trust | RAG action | Confidence | Reasons |
|---|---|---|---|---|---|
| t_p_120_1176_p000001 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000003 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000005 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000006 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000007 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000008 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000009 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000010 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000017 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000024 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000028 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000029 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000030 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000031 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000032 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000033 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000034 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000036 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000037 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |
| t_p_120_1176_p000038 | part_catalog | A | include_as_verified_part_evidence | 0.871625 | verified_part_evidence_selected; safe_for_verified_part_index |

## Derived context samples
| Page | Layer | Trust | RAG action | Confidence | Reasons |
|---|---|---|---|---|---|
| t_p_120_1176_p000003 | table_tile_text_refined | A | include_as_derived_context | 0.881125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000003 | table_tile_text_refined | A | include_as_derived_context | 0.881125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000003 | table_tile_text_refined | A | include_as_derived_context | 0.881125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000003 | table_tile_text_refined | A | include_as_derived_context | 0.881125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000003 | table_tile_text_refined | A | include_as_derived_context | 0.881125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000003 | table_tile_text_refined | A | include_as_derived_context | 0.881125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000005 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000005 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000005 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000006 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000006 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000006 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000007 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000007 | table_tile_text_refined | B | include_as_derived_context | 0.64125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000008 | table_tile_text_refined | B | include_as_derived_context | 0.64125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000008 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000008 | table_tile_text_refined | B | include_as_derived_context | 0.64125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000009 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000009 | table_tile_text_refined | B | include_as_derived_context | 0.64125 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |
| t_p_120_1176_p000010 | table_tile_text_refined | B | include_as_derived_context | 0.75525 | refined_table_tile_text_selected; derived_context_only; not_canonical_source_truth |

## Excluded samples
| Page | Layer | Trust | RAG action | Confidence | Reasons |
|---|---|---|---|---|---|
| t_p_120_1176_p000078 | part_catalog | C | exclude_from_rag | 0.767125 | excluded_by_stage5_decision |
| t_p_120_1176_p000491 | part_catalog | C | exclude_from_rag | 0.767125 | excluded_by_stage5_decision |
| t_p_120_1176_p000001 | visual_text | C | exclude_from_rag | 0.767125 | excluded_by_stage5_decision |
| t_p_120_1176_p000003 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000004 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000005 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000006 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000007 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000008 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000009 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000010 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000011 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000013 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000014 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000015 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000016 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000017 | visual_text | C | exclude_from_rag | 0.40375 | excluded_by_stage5_decision |
| t_p_120_1176_p000018 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000019 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |
| t_p_120_1176_p000020 | visual_text | C | exclude_from_rag | 0.37875 | excluded_by_stage5_decision |

