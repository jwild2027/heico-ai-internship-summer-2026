# TRACE-Net Answer Context Evidence Enricher v1

`trace_net_answer_context_evidence_enricher_v1` enriches an answer context engineering pack with source-traceable OCR/table/page/image excerpts.

It is dry-run only. It does not write to Postgres, Qdrant, or OpenSearch. It does not mutate source truth. It does not grant answer permission.

## Inputs

Required:

- `--context-pack`: `trace_net_answer_context_engineering_pack_v1.json`
- `--ocr-route-scan-pack`: `trace_net_ocr_route_scan_pack_v1.json`
- `--output-dir`: output directory

Optional:

- `--table-exact-search-adapter`: table/exact evidence artifact to prefer over raw OCR excerpts
- `--page-context-v2`: page summary artifact for fallback context
- `--image-visual-summary`: image route visual summary artifact for image evidence
- `--excerpt-window-chars`: excerpt size window around detected query part numbers

## Outputs

- `trace_net_answer_context_evidence_enricher_v1.json`
- `trace_net_answer_context_evidence_enricher_v1_prompt.txt`
- `trace_net_answer_context_evidence_enricher_v1_records.jsonl`
- `trace_net_answer_context_evidence_enricher_v1_records.csv`
- `trace_net_answer_context_evidence_enricher_v1_citation_map.jsonl`
- `trace_net_answer_context_evidence_enricher_v1_violations.csv`
- `trace_net_answer_context_evidence_enricher_v1_summary.json`
- `trace_net_answer_context_evidence_enricher_v1_quality_check.json`

## Build example

```bash
python scripts/build_trace_net_answer_context_evidence_enricher_v1.py \
  --context-pack local_data/organization/trace_net/answer_context_engineering_pack_gemma4_native_001/trace_net_answer_context_engineering_pack_v1.json \
  --ocr-route-scan-pack local_data/organization/trace_net/raw_to_answer_e2e_smoke_gemma4_native_001/ocr_route_scan_pack_tesseract_full/trace_net_ocr_route_scan_pack_v1.json \
  --table-exact-search-adapter local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json \
  --page-context-v2 local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json \
  --image-visual-summary local_data/organization/trace_net/image_visual_summary_llava_12_pages/trace_net_image_visual_summary_v1.json \
  --output-dir local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001 \
  --require-source-quality-pass \
  --quality
```

## Quality check example

```bash
python scripts/check_trace_net_answer_context_evidence_enricher_v1_quality.py \
  --report-path local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001/trace_net_answer_context_evidence_enricher_v1.json \
  --write-json \
  --min-records 1 \
  --min-enriched-excerpts 1 \
  --min-citations 1 \
  --min-prompt-chars 500 \
  --max-violation-records 0 \
  --require-source-quality-pass \
  --require-enriched-prompt \
  --require-no-human-review-required \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts
```

## Safety contract

- `answer_permission=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`
- `dry_run_only=true`
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
