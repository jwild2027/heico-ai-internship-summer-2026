# TRACE-Net Table Cell Normalizer v1 Safety Fix

This patch fixes the Step 15.1 quality gate for table cell normalization.

The first Step 15.1 implementation counted provenance fields from the source
`table_understanding` record, such as source paths or internal trace metadata,
as `unsafe_table_evidence`. That was too strict for an internal artifact and
caused clean table normalization records to fail quality when their parent table
record contained source-trace metadata.

The corrected behavior is:

- Inspect only user-visible extracted/normalized table text fields.
- Continue blocking real leaks inside row/cell/snippet text.
- Do not treat source-trace provenance in parent records as unsafe evidence.
- Keep all table rows behind source, citation, and authority gates.
- Do not allow table rows to answer directly or mutate source truth.

Expected result on the current local artifacts:

```text
normalized_table_record_count: 495
normalized_row_count: 1414
normalized_cell_count: 3090
part_number_merge_candidate_count: 2
catalog_supported_merge_count: 2
answer_support_row_count: 287
unsafe_table_evidence_count: 0
Quality status: PASS
```
