# TRACE-Net Raw-to-Answer E2E Smoke Native v1

Runs the full TRACE-Net OCR/classifier pipeline, performs local validated-payload retrieval, and drafts a citation-backed answer with Ollama's native `/api/chat` endpoint.

This exists because `gemma4:26b` can return reasoning-only output with empty `message.content` through the OpenAI-compatible `/v1/chat/completions` endpoint. Native Ollama chat with `think:false` returns final answer content correctly.

## Safety contract

- Dry-run storage only.
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission granted.

## Example

```bash
python scripts/run_trace_net_raw_to_answer_e2e_smoke_native_v1.py \
  --source-package /c/Users/juswil/Desktop/metadata.zip \
  --tesseract-cmd "/c/Users/juswil/AppData/Local/Programs/Tesseract-OCR/tesseract.exe" \
  --output-dir local_data/organization/trace_net/raw_to_answer_e2e_smoke_gemma4_native_001 \
  --question "Find part number 120-29073-001 and nearby similar parts. Use TRACE-Net evidence and cite pages." \
  --llm-mode ollama_native \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gemma4:26b \
  --llm-think false \
  --llm-num-predict 1024 \
  --request-timeout 600 \
  --require-llm-success \
  --quality
```
