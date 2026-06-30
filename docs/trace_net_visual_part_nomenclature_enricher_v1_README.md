# TRACE-Net Visual Part Nomenclature Enricher v1

This module enriches already-linked image/diagram evidence with trusted part nomenclature/description fields from table/OCR/exact evidence artifacts.

It is deliberately evidence-only:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
- no LLaVA rerun
- no endpoint/OpenWebUI code changes

## Inputs

- `trace_net_image_visual_evidence_pack_v1.json`
- trusted table/exact evidence artifacts, especially `trace_net_table_route_evidence_packager_v1.json`

## Outputs

- `trace_net_visual_part_nomenclature_enricher_v1.json`
- `trace_net_visual_part_nomenclature_enricher_v1_quality_check.json`
- `trace_net_visual_part_nomenclature_missing_report_v1.json`
- `trace_net_visual_part_nomenclature_enriched_records_v1.csv`

## Confidence rule

This module does not upgrade visual identity proof by itself. It only enriches linked part records with descriptions when those descriptions are found in trusted evidence rows. LLaVA remains observation-only.
