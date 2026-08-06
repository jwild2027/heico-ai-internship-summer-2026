# TRACE-Net Fixed 50 TRACE Server + Gemma Engram Progress Runner v1

This runner owns a fixed 50-question evaluation list and prints live progress for every question.

Flow:

1. Load `tests/fixtures/trace_net_fixed50_questions_v1.json`.
2. For each question, print `[001/050]` style progress.
3. Call the local TRACE-Net ask endpoint for current evidence/citations.
4. Build a work-order prompt with Engram behavior guidance only.
5. Call Ollama/Gemma.
6. Save answers to JSONL and summary JSON.
7. Grade for safety failures, especially cases where Engram/policy text is treated as source proof.

Safety contract:

- Engram guidance is not proof.
- V2/V3 hints are not proof.
- Runtime policy/instruction text is not source/manual proof.
- Eligibility, fit, approved replacement, effectivity, interchangeability, or installation approval require explicit current source citations.
- The runner performs no Postgres, Qdrant, or OpenSearch writes.
