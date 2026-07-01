# TRACE-Net Engineering Engram Prompt Injector v1

H16 extends the engineering LLM answer smoke runner so it can consume an H15 Engineering Engram Core JSON profile and inject relevant behavior memories into the prompt.

The engram block is **behavior guidance only**. It is not source-truth proof, cannot be cited as evidence, does not grant answer permission, and does not mutate source artifacts or databases.

## Inputs

- H15 `trace_net_engineering_engram_core_v1.json`
- H13/H14C LLM smoke inputs: planner/context evidence packs and optional question bank

## Outputs

- Existing H13/H14C smoke manifest outputs
- Prompt files with `TRACE_NET_ENGINEERING_ENGRAM_MEMORY`
- Safe reasoning trace fields:
  - `engram_atom_count`
  - `engram_ids`
  - `engram_traits`

## Safety

- No writes to Postgres, Qdrant, or OpenSearch
- No source-truth mutation
- No answer permission
- Engram memory is never proof and is never citable evidence
