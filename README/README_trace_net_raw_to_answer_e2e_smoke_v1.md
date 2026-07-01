# TRACE-Net Raw-to-Answer E2E Smoke v1

Dry-run end-to-end smoke test:

raw TIFF package -> OCR/classifier pipeline -> retrieval payload audit -> local artifact retrieval -> citation-backed answer draft.

The smoke is intentionally safe by default:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission

## Gemma/Ollama mode

Use Ollama's OpenAI-compatible endpoint with a large token budget. Some Gemma models emit reasoning before final content; if `max_tokens` is too small, Ollama may return empty `message.content` with non-empty `message.reasoning` and `finish_reason=length`. This module now records that fallback reason and can fail quality when `--require-llm-success` is set.

```bash
python scripts/run_trace_net_raw_to_answer_e2e_smoke_v1.py \
  --source-package /c/Users/juswil/Desktop/metadata.zip \
  --tesseract-cmd "/c/Users/juswil/AppData/Local/Programs/Tesseract-OCR/tesseract.exe" \
  --output-dir local_data/organization/trace_net/raw_to_answer_e2e_smoke_gemma4_strict_001 \
  --question "Find part number 120-29073-001 and nearby similar parts. Use TRACE-Net evidence and cite pages." \
  --llm-mode ollama_openai \
  --llm-base-url http://127.0.0.1:11434/v1 \
  --llm-model gemma4:26b \
  --llm-api-key ollama \
  --request-timeout 600 \
  --llm-max-tokens 2048 \
  --require-llm-success \
  --quality
```

Quality check with strict LLM success:

```bash
python scripts/check_trace_net_raw_to_answer_e2e_smoke_v1_quality.py \
  --report-path local_data/organization/trace_net/raw_to_answer_e2e_smoke_gemma4_strict_001/trace_net_raw_to_answer_e2e_smoke_v1.json \
  --write-json \
  --min-stage-reports 9 \
  --min-postgres-contract-ready 509 \
  --min-qdrant-contract-ready 400 \
  --min-opensearch-contract-ready 250 \
  --min-qdrant-payloads 400 \
  --min-opensearch-payloads 250 \
  --min-retrieval-evidence 1 \
  --min-citations 1 \
  --max-violations 0 \
  --require-all-stage-quality-pass \
  --require-dry-run-only \
  --require-no-human-review-required \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts \
  --require-llm-success
```
