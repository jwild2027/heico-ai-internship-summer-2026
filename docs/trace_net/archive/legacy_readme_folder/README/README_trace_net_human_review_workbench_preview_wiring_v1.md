# TRACE-Net Human Review Workbench Source/Image Preview Wiring v1

Adds a read-only enrichment layer over `trace_net_human_review_workbench_v1.json` so page-scoped review cards and page profiles include TIFF/source-package preview metadata from `trace_net_dublin_core_source_package_extension_v1.json`.

## Purpose

The base workbench organizes review tasks, triage cards, visual/table/category summaries, and allowed reviewer decisions. This module wires in source package provenance so reviewers can see which TIFF/METS entry belongs to a page.

It adds fields such as:

- source package label / object ID / language
- TIFF entry name, for example `00000003.tif`
- METS href, for example `file://./00000003.tif`
- source package page number
- TIFF size bytes
- SHA-1 checksum
- checksum match flag
- source traceability status
- viewer hint for a future UI

## Safety

This module is metadata-only. It does not load image bytes and does not write to Postgres, Qdrant, OpenSearch, graph truth, source truth, citations, trust records, or answers.

All preview records remain:

```text
can_answer_directly = false
can_prove_claims = false
source_truth_mutation_allowed = false
final_answer_allowed = false
```

## Build

```bash
python scripts/build_trace_net_human_review_workbench_preview_wiring_v1.py \
  --human-review-workbench local_data/organization/trace_net/human_review_workbench/trace_net_human_review_workbench_v1.json \
  --dublin-core-source-package-extension local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json \
  --output-dir local_data/organization/trace_net/human_review_workbench_preview \
  --min-workbench-cards 544 \
  --min-page-profiles 509 \
  --min-page-scoped-cards 492 \
  --min-cards-with-page-preview 492 \
  --min-cards-with-source-package-summary 492 \
  --min-page-profiles-with-preview 509 \
  --require-source-workbench-quality-pass \
  --require-source-package-quality-pass \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_human_review_workbench_preview_wiring_v1_quality.py \
  --report-path local_data/organization/trace_net/human_review_workbench_preview/trace_net_human_review_workbench_preview_wiring_v1.json \
  --min-workbench-cards 544 \
  --min-page-profiles 509 \
  --min-page-scoped-cards 492 \
  --min-cards-with-page-preview 492 \
  --min-cards-with-source-package-summary 492 \
  --min-page-profiles-with-preview 509 \
  --require-source-workbench-quality-pass \
  --require-source-package-quality-pass \
  --write-json
```

## Expected output shape

```text
TRACE-Net Human Review Workbench Source/Image Preview Wiring v1
 Status: HUMAN_REVIEW_WORKBENCH_PREVIEW_WIRING_BUILT
 Quality status: PASS
 workbench_card_count: 544
 page_scoped_workbench_card_count: 492
 cards_with_page_preview_count: 492
 cards_with_source_package_summary_count: 492
 missing_page_preview_for_page_scoped_card_count: 0
 cards_with_checksum_mismatch_count: 0
 source_truth_mutation_allowed_count: 0
```
