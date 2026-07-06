# TRACE-Net Engineering Engram Answer Runner Retrieval Bridge v1 (H23)

H23 creates the artifact-only bridge between retrieved Engram prompt guidance and the real engineering answer runner.

It does **not** patch the full answer runner yet and does not launch a long 30-question smoke. Instead, it produces a deterministic guidance map keyed by task type so the next patch can wire retrieval-guided behavior into targeted answer-runner prompts behind an explicit flag.

## Inputs

- H20 `engineering_engram_prompt_retrieval_injector_v1` manifest.
- Optional H22 `engineering_engram_prompt_retrieval_llm_smoke_v1_ollama` manifest.

## Outputs

- `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.json`
- `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_records.jsonl`
- `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_guidance_map.json`
- `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_quality_check.json`

## Safety contract

- Engram retrieval is behavior guidance only.
- Manual/source claims still require current `proof_context` citations.
- No live Qdrant IO is attempted.
- No Postgres, Qdrant, or OpenSearch writes are attempted.
- No source-truth mutation is allowed.
- Engram memory cannot grant answer permission.

## Next step

H24 should wire this guidance map into a small targeted engineering answer-runner smoke, such as q12/q16/q18/q25/q29, before any full 30-question run.

## v1b boundary safety repair

H23 v1b relaxes boundary matching so normal H20 wording such as `BEHAVIOR ONLY, NOT PROOF` and `shape answer behavior only` is treated as a valid safety boundary. The previous H23 matcher required the exact phrase `behavior guidance only`, which caused false unsafe findings even when the prompt clearly said Engram guidance is behavior-only and not proof.
