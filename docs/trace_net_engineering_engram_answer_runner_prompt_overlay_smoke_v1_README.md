# TRACE-Net Engineering Engram Answer-Runner Prompt Overlay Smoke v1

H24 turns the H23 answer-runner retrieval bridge into an artifact-only prompt overlay map for a small targeted set of answer-runner questions.

## Purpose

The full 30-question LLM smoke is slow. H24 creates a targeted overlay smoke so retrieved Engram guidance can be inspected before it is wired into a live answer-runner LLM path.

## Inputs

- H23 answer-runner retrieval bridge manifest.
- Optional existing engineering answer smoke manifest, such as H16D 30-question PASS, for question metadata.

## Outputs

- `trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.json`
- `trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_records.jsonl`
- `trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_overlay_map.json`
- quality check JSON

## Safety contract

Artifact-only:

- no answer permission
- no source-truth mutation
- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no write attempts

Engram overlays are behavior guidance only. Manual/source claims still require current `proof_context` citations.

## Next step

H25 should use this overlay map in a targeted LLM answer-runner overlay smoke, for example q12, q16, q18, q25, and q29.
