# TRACE-Net Engineering Engram Core v1

H15 creates the first versioned TRACE-Net Engineering Engram: a local JSON behavior-memory pack that stores operational engineering traits, source-trace policies, route behavior rules, eval failure memories, Self-RAG critic traits, and CRAG repair traits.

This stage does **not** write to Postgres, Qdrant, OpenSearch, or source-truth records. It only builds local JSON/CSV artifacts that later stages can inject into prompts or load into vector memory.

## Outputs

- `trace_net_engineering_engram_core_v1.json`
- `trace_net_engineering_engram_memory_atoms_v1.json`
- `trace_net_engineering_engram_traits_v1.json`
- `trace_net_engineering_engram_core_v1_quality_check.json`
- `trace_net_engineering_engram_memory_atoms_v1.csv`

## Purpose

The Engram Core makes TRACE-Net behave like a consistent engineering analyst:

- shared nomenclature is not interchangeability
- figure identity is not installation safety
- v2 summaries guide but do not prove
- visual links establish figure-to-part identity
- OCR nomenclature provides source-trace-ready name text
- table/OCR supports exact part presence, not approval
- pipeline/debug questions should explain route behavior
- prior eval failures become repair memories

## Next stages

- H16: Engram Prompt Injector
- H17: Engram Vector Loader for Qdrant
- H18: Self-RAG Engram Critic
- H19: CRAG Engram Repair
