# TRACE-Net Raw-to-Answer Context-Engineered Native v1

This module integrates the context-engineering chain into a single dry-run E2E runner:

1. Run the OCR/classifier pipeline over the raw TIFF package.
2. Run exact part-number retrieval against trusted OCR/table/page artifacts.
3. Inject direct exact anchors into the answer context.
4. Expand context with anchor-aware graph/Leiden communities.
5. Call Gemma4 through Ollama native `/api/chat` with `think=false`.
6. Write a source-traced report, answer markdown, and quality check.

The runner is dry-run only. It does not write to Postgres, Qdrant, or OpenSearch, does not mutate source truth, and does not grant answer permission.

## Build

```bash
python scripts/run_trace_net_raw_to_answer_context_engineered_native_v1.py \
  --source-package /c/Users/juswil/Desktop/metadata.zip \
  --tesseract-cmd "/c/Users/juswil/AppData/Local/Programs/Tesseract-OCR/tesseract.exe" \
  --output-dir local_data/organization/trace_net/raw_to_answer_context_engineered_native_gemma4_001 \
  --question "Find part number 120-29073-001 and nearby similar parts. Use TRACE-Net evidence and cite pages." \
  --part-number 120-29073-001 \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gemma4:26b \
  --llm-think false \
  --llm-num-predict 1200 \
  --request-timeout 600 \
  --require-source-quality-pass \
  --require-anchor-communities \
  --require-llm-success \
  --quality
```

## Check

```bash
python scripts/check_trace_net_raw_to_answer_context_engineered_native_v1_quality.py \
  --report-path local_data/organization/trace_net/raw_to_answer_context_engineered_native_gemma4_001/trace_net_raw_to_answer_context_engineered_native_v1.json \
  --write-json \
  --min-stage-reports 12 \
  --min-postgres-contract-ready 509 \
  --min-qdrant-contract-ready 400 \
  --min-opensearch-contract-ready 250 \
  --min-qdrant-payloads 400 \
  --min-opensearch-payloads 250 \
  --min-direct-exact-anchors 8 \
  --min-anchor-communities 1 \
  --min-citations 8 \
  --min-prompt-chars 500 \
  --max-violations 0 \
  --require-all-stage-quality-pass \
  --require-context-engineering-enabled \
  --require-anchor-aware-prompt \
  --require-dry-run-only \
  --require-no-human-review-required \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts \
  --require-llm-success
```
