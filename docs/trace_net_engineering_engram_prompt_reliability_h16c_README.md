# TRACE-Net H16C Engram Prompt Reliability

H16C fixes the H16B full 30-question Engram smoke failure mode where Ollama/Gemma returned a non-empty but truncated answer. The observed q18 answer stopped mid-sentence at `which allows the system to` / `OCR-backed`, so H16B did not retry because it only retried empty responses.

## What this patch adds

- `tiff/trace_net_h16c_llm_answer_reliability_v1.py`
  - Detects incomplete answer shapes.
  - Supplies safer Ollama generation defaults: `num_predict=900`, `temperature=0.1`.
  - Provides a safety contract: no DB writes, no vector writes, no search writes, no source-truth mutation, no answer permission.
- `scripts/apply_trace_net_h16c_incomplete_retry_patch_v1.py`
  - Applies a conservative source patch to `tiff/trace_net_engineering_llm_answer_smoke_v1.py`.
  - Inserts Ollama options into local `/api/generate` payloads.
  - Raises a retryable `RuntimeError` when the answer looks incomplete, letting the existing H16B retry/fallback path handle it.
- `scripts/filter_trace_net_engineering_llm_question_bank_v1.py`
  - Makes targeted reruns possible by creating a one-question JSONL bank, e.g. q18 only.

## Safety contract

H16C changes only local generation reliability. It does not grant answer permission and does not mutate source truth. It does not write to Postgres, Qdrant, or OpenSearch. Engram memory remains behavior guidance only; proof still comes only from proof_context citations.

## Expected result

Targeted q18 should no longer stop mid-sentence. Final full 30-question H16C smoke should reach at least 28 GOOD with q25/q26 allowed as expected unknown-case PARTIAL records, while keeping:

- bad answers = 0
- unsupported claims = 0
- summary used as proof = 0
- invalid citations = 0
- write attempts = 0
