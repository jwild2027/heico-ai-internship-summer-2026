# TRACE-Net TIFF Content Gemma Evidence Pack Router v3

This runner is a focused follow-up to router v2. It keeps the local artifact evidence-pack route, but adds deterministic structured summaries and fallbacks so useful routed evidence is not discarded when Gemma returns a blank or near-blank response.

## What changed from v2

- Extracts page IDs from both artifact text and artifact source paths.
- Adds deterministic evidence summaries for ATA, document title, revision, figure/page, visual, nomenclature, part, table, manual keyword, and summary routes.
- Includes the deterministic route summary in the Gemma prompt as a grounded starting point.
- If Gemma returns blank, uses the deterministic route summary instead of a generic no-proof fallback when one is available.
- Adds `deterministic_fallback_available_count` and `unresolved_fallback_count` to `summary.json`.
- Keeps the same read-only safety contract: no source-truth mutation, no DB writes, no answer permission.

## Server command

```bash
PYTHONUNBUFFERED=1 python3 -u scripts/run_trace_net_tiff_content_gemma_evidence_pack_router_v3.py \
  --questions /data/trace_net_runs/tiff_content_gemma_questions_50.json \
  --artifact-root local_data/organization/trace_net \
  --output-dir /data/trace_net_runs/tiff_content_gemma_evidence_pack_router_v3 \
  --ollama-host http://127.0.0.1:11434 \
  --model gemma4:26b \
  --top-k 18 \
  2>&1 | tee /data/trace_net_runs/tiff_content_gemma_evidence_pack_router_v3.log
```

## Outputs

- `answers.jsonl`
- `question_answer_view.txt`
- `evidence_debug.jsonl`
- `prompts/`
- `summary.json`
