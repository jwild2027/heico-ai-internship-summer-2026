# TRACE-Net Table Cell Normalizer / Part Row Repair v1

Step 15.1 refines Step 15 table-understanding output. It normalizes table rows/cells, detects split part-number cells, repairs them conservatively, and keeps every row behind TRACE-Net source/citation/authority gates.

It is read-only:

- does not mutate Postgres
- does not mutate Qdrant
- does not mutate source truth
- does not allow direct answers
- does not promote retrieval-only rows into answer proof

## Inputs

```text
local_data/organization/trace_net/table_understanding/trace_net_table_understanding_v1.json
local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json
local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json
```

The embedding candidates file is used only as a catalog/part-pattern reference. A split part-number repair is marked `catalog_supported` only when the repaired part appears in known candidate/catalog text.

## Algorithm

```text
trace_net_table_cell_normalizer_part_row_repair_v1
```

The algorithm:

1. Cleans cell text while preserving hyphens used by part numbers and ATA codes.
2. Classifies cell kinds such as `part_number`, `part_fragment_left`, `part_fragment_right`, `ata_code`, `date`, `ipl_reference`, and `index_label`.
3. Detects adjacent split part-number fragments.
4. Repairs adjacent fragments only when the joined value matches the canonical part pattern `000-00000-000`.
5. Marks repairs as `catalog_supported` or `candidate_unverified`.
6. Classifies row types such as `part_catalog_row`, `part_number_row`, `revision_effectivity_row`, `index_or_header_row`, and `structured_text_row`.
7. Keeps all rows non-answering until later final answer gates.

Example repair:

```text
['120-46', '137-001'] -> 120-46137-001
```

## Outputs

```text
local_data/organization/trace_net/table_cell_normalizer/
  trace_net_table_cell_normalizer_v1.json
  trace_net_table_cell_normalizer_v1_records.jsonl
  trace_net_table_cell_normalizer_v1_rows.jsonl
  trace_net_table_cell_normalizer_v1_cells.jsonl
  trace_net_table_cell_normalizer_v1_repairs.jsonl
  trace_net_table_cell_normalizer_v1_graph_attachment_plan.jsonl
  trace_net_table_cell_normalizer_v1_summary.json
  trace_net_table_cell_normalizer_v1_manifest.json
  trace_net_table_cell_normalizer_v1_quality.json
  trace_net_table_cell_normalizer_v1.md
  trace_net_table_cell_normalizer_v1.html
```

## Safety contract

All normalized table rows keep:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
final_answer_allowed = false
```

A row may become an `answer_support_candidate`, but that only means it can be considered by later context/final-answer gates. It still cannot answer directly.

## Build

```bash
python scripts/build_trace_net_table_cell_normalizer_v1.py \
  --table-understanding local_data/organization/trace_net/table_understanding/trace_net_table_understanding_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --output-dir local_data/organization/trace_net/table_cell_normalizer \
  --min-normalized-table-records 20 \
  --min-normalized-rows 100 \
  --min-normalized-cells 100 \
  --min-part-number-merge-candidates 1 \
  --min-answer-support-rows 1 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_table_cell_normalizer_v1_quality.py \
  --report-path local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --min-normalized-table-records 20 \
  --min-normalized-rows 100 \
  --min-normalized-cells 100 \
  --min-part-number-merge-candidates 1 \
  --min-answer-support-rows 1 \
  --write-json
```

## Quality gates

The checker requires:

```text
normalized_table_record_count >= threshold
normalized_row_count >= threshold
normalized_cell_count >= threshold
part_number_merge_candidate_count >= threshold
answer_support_row_count >= threshold
unsafe_table_evidence_count = 0
uncited_answer_capable_row_count = 0
retrieval_only_answer_allowed_count = 0
source_truth_mutation_allowed_count = 0
final_answer_allowed_count = 0
```
