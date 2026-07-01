# TRACE-Net OCR Classifier Pipeline Runner v1

Single-command dry-run orchestrator for the current TRACE-Net OCR/classifier pipeline.

## What it runs

1. OCR route scan pack
2. Route confidence resolver
3. Four-route operational resolver
4. Route validator runner
5. Unresolved retry/probe
6. Four-route storage gate
7. Dry-run loader planner
8. Loader contract audit
9. Retrieval payload audit

The pipeline is dry-run only. It does not write to Postgres, Qdrant, or OpenSearch. It does not grant answer permission. It does not mutate source truth.

## Command

```bash
python scripts/run_trace_net_ocr_classifier_pipeline_v1.py \
  --source-package /c/Users/juswil/Desktop/metadata.zip \
  --tesseract-cmd "/c/Users/juswil/AppData/Local/Programs/Tesseract-OCR/tesseract.exe" \
  --output-dir local_data/organization/trace_net/ocr_classifier_rerun_002 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_ocr_classifier_pipeline_v1_quality.py \
  --report-path local_data/organization/trace_net/ocr_classifier_rerun_002/trace_net_ocr_classifier_pipeline_runner_v1.json \
  --write-json \
  --min-stage-reports 9 \
  --min-postgres-contract-ready 509 \
  --min-qdrant-contract-ready 400 \
  --min-opensearch-contract-ready 250 \
  --min-qdrant-payloads 400 \
  --min-opensearch-payloads 250 \
  --max-violation-records 0 \
  --require-all-stage-quality-pass \
  --require-dry-run-only \
  --require-no-human-review-required \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts
```

## Outputs

- `trace_net_ocr_classifier_pipeline_runner_v1.json`
- `trace_net_ocr_classifier_pipeline_runner_v1_summary.json`
- `trace_net_ocr_classifier_pipeline_runner_v1_command_records.jsonl`
- all normal stage artifacts under the output directory

## Expected baseline for the current 509-page manual

- blank: 14
- plain_text: 163
- table: 320
- image: 12
- Postgres contract ready: 509
- Qdrant contract ready: 450
- OpenSearch contract ready: 282
- retrieval payload violations: 0
- missing lineage: 0
- human review required: 0
