# TRACE-Net Guided Candidate Discovery v1

Adds a low-context candidate-discovery runner for partial part lookup and weak user clues.

## Purpose

This module handles questions such as:

- `I only know the part starts with 24.`
- `I know it has 04 somewhere and looked like a bolt near a seat.`
- `I need a part in ATA 25 but only know two digits.`

It does **not** claim a final part identity. It returns candidate routes plus clarifying questions.

## Safety contract

- Read-only artifact scanning.
- No source-truth mutation.
- No Postgres/Qdrant/OpenSearch writes.
- `final_answer_allowed=false` for candidate routes.
- Candidate routes are discovery hints, not proof of eligibility, fit, approval, interchangeability, installation approval, or effectivity.

## Outputs

- `candidate_discovery_results.jsonl` — structured candidate route records.
- `candidate_discovery_view.txt` — clean user-facing route cards.
- `summary.json` — run summary and safety counts.
- `prompts/` — per-question candidate-discovery packs for UI/LLM use.

## Example server run

```bash
PYTHONUNBUFFERED=1 python3 -u scripts/run_trace_net_guided_candidate_discovery_v1.py \
  --artifact-root local_data/organization/trace_net \
  --output-dir /data/trace_net_runs/guided_candidate_discovery_v1 \
  --question "I am looking for a part that starts with numbers 2 and 4 but do not have the rest" \
  --top-k 8 \
  2>&1 | tee /data/trace_net_runs/guided_candidate_discovery_v1.log
```

Optional LLM rendering is available with `--use-ollama --ollama-host http://127.0.0.1:11434 --model gemma4:26b`, but the structured JSON remains the source of truth.
