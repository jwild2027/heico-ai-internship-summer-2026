# TRACE-Net H14C Engineering LLM Smoke Path + Safe Reasoning Trace v1

This patch updates `tiff/trace_net_engineering_llm_answer_smoke_v1.py` after the H14B rerun exposed two remaining issues:

1. Some nested runner/context-pack quality-check writes failed under long H14B output paths on Windows.
2. The user wanted to inspect the LLM's reasoning process. This patch does **not** expose raw hidden chain-of-thought. Instead, it writes a safe reasoning trace for every question: question, category, selected proof-context citations, prompt/scaffold status, answer path, gate result, and any runner/LLM error.

## Changes

- Shortens H13/H14 LLM smoke stage directories:
  - `runs` -> `r`
  - `prompts` -> `p`
  - `llm_answers` -> `a`
  - runner stage folder `runner` -> `r`
  - run folders become short hash-backed names like `q01_04f8cb`.
- Adds per-question safe reasoning trace JSON files under `t/`.
- Adds `reasoning_trace_path` to records and CSV output.
- Preserves the full question text in JSON records.
- Keeps all safety gates: no unsupported positive approval/interchangeability/safety claims, no summary-as-proof, no DB writes, no source-truth mutation.

## Safe reasoning trace policy

The trace is not hidden chain-of-thought. It is an audit/debug trace containing:

- proof-context citation labels supplied to the LLM
- prompt intent rules
- whether a structured TRACE-Net scaffold was provided
- answer/gate counts
- any runner or LLM error
- answer preview

## Safety contract

- No writes to Postgres/Qdrant/OpenSearch.
- No source-truth mutation.
- No answer permission granted.
- Local JSON/CSV/prompt/answer/trace artifacts only.
