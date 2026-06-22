# TRACE-Net Table Route Value Normalizer v1

Converts table-route cell extractor values into fielded, source-traceable retrieval records.

## Inputs

- `local_data/organization/trace_net/table_route_cell_extractor/trace_net_table_route_cell_extractor_v1.json`

## Outputs

- `trace_net_table_route_value_normalizer_v1.json`
- `trace_net_table_route_value_normalizer_v1_records.jsonl`
- `trace_net_table_route_value_normalizer_v1_values.jsonl`
- `trace_net_table_route_value_normalizer_v1_summary.json`
- `trace_net_table_route_value_normalizer_v1_quality.json`
- `trace_net_table_route_value_normalizer_v1_manifest.json`

## Safety contract

This module is retrieval/evidence preparation only. It does not grant answer permission and does not write to Postgres, Qdrant, OpenSearch, or source-truth artifacts.

## Fielded evidence examples

- `covered_part_number`
- `manual_page_reference`
- `page_rev_or_sequence_value`
- `ipl_part_number`
- `ipl_figure_item_or_quantity`
- `ipl_text`

## LEP row reconstruction behavior

This module tightens `LIST OF EFFECTIVE PAGES` normalization:

- suppresses noisy `lep_other` body fragments instead of emitting every fragment as `lep_context`
- reconstructs fragmented page references from whole rows, for example `25-21 -00- 103` -> `25-21-00-103`
- labels row-derived references with `lep_row_derived_manual_page_reference`
- marks existing single-cell manual references as row-derived when row parsing verifies them
- preserves one low-confidence `lep_table_presence_context` marker for extraction-ready LEP tables that have no fielded row values, keeping table coverage without reintroducing noisy body fragments
- reports `lep_context_suppressed_record_count`, `lep_row_derived_manual_page_reference_record_count`, and `lep_row_derived_page_rev_or_sequence_value_record_count`

The module remains retrieval-only and does not mutate route/source truth.
