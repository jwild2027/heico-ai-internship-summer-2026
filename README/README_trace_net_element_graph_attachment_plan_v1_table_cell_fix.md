# TRACE-Net Element Graph Attachment Plan v1 Table Cell Link Fix

This patch fixes Step 18 table-cell graph planning for Step 15.1 normalized table artifacts.

Step 15.1 normalized rows may expose `normalized_row_id` and `source_row_id`, while normalized cells keep `row_id` as the source row id. The original Step 18 planner matched cells only against `row_id`, so it created `TableRow` nodes but no `TableCell` nodes for real normalized table records.

The fix adds robust row/cell alias matching:

- `row_id`
- `normalized_row_id`
- `source_row_id`
- `row_index`
- fallback row-number aliases

It also prefers Step 15.1 identifiers:

- `normalized_table_id`
- `normalized_cell_id`
- `normalized_text`
- `normalized_kind`

The output remains read-only and does not mutate Postgres, Qdrant, source data, graph truth, or trust records.

Expected repaired Step 18 result:

```text
Quality status: PASS
table_cell_node_plan_count: >= 100
orphan_edge_count: 0
answer_capable_without_citation_count: 0
source_truth_mutation_allowed_count: 0
```
