# TRACE-Net Fishnet Route Signal Workbench v1

Read-only comparison workbench for fishnet OCR/grid route candidates versus the current TRACE-Net page route manifest.

## v1.2 fix

The v1.2 patch carries nested fishnet OCR diagnostics into the workbench comparison records. Fishnet v1.4/v1.5 stores OCR information under `page_ocr_features`, so older workbench builds reported `fishnet_ocr_text_length: 0` even when OCR was healthy. v1.2 now carries:

- `fishnet_ocr_text_length`
- `fishnet_ocr_word_count`
- `fishnet_ocr_word_box_count`
- `fishnet_ocr_sample_text`
- `fishnet_best_route_candidate_before_review`
- `fishnet_review_reason_codes`
- `fishnet_route_adjusted_scores`
- `fishnet_reason_counts`

The workbench remains review-only. It never changes the official page route manifest.

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
- route changes are not authorized

## Build

```bash
python scripts/build_trace_net_fishnet_route_signal_workbench_v1.py \
  --fishnet-report local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json \
  --current-route-manifest local_data/organization/trace_net/page_route_manifest/trace_net_page_route_manifest_v1.json \
  --trace-net-root local_data/organization/trace_net \
  --output-dir local_data/organization/trace_net/fishnet_route_signal_workbench \
  --high-confidence-threshold 0.85 \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_fishnet_route_signal_workbench_v1_quality.py \
  --report-path local_data/organization/trace_net/fishnet_route_signal_workbench/trace_net_fishnet_route_signal_workbench_v1.json \
  --write-json \
  --require-page-count 509 \
  --min-comparison-records 509 \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-current-routes \
  --max-missing-current-routes 0 \
  --min-fishnet-ocr-text-chars 400000 \
  --min-fishnet-ocr-word-boxes 10000 \
  --min-pages-with-fishnet-ocr-text 495
```
