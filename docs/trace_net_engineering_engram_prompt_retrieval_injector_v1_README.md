# TRACE-Net Engineering Engram Prompt Retrieval Injector v1

H20 converts H19 Engram vector retrieval results into compact prompt guidance blocks.

## Purpose

H17 defines typed Engram memory layers. H18 exports those atoms as Qdrant-ready local vector records. H19 retrieves relevant atoms for a task/query. H20 packages the retrieved atoms into an LLM-ready prompt section.

The prompt section is explicitly **behavior guidance only, not proof**.

## Safety contract

H20 is artifact-only:

- no Postgres writes
- no Qdrant reads or writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission

## Proof boundary

Engram retrieval may shape answer behavior, style, repair patterns, and route awareness. It cannot prove manual facts. Source claims still require current TRACE-Net `proof_context` citations.

## Output

- `trace_net_engineering_engram_prompt_retrieval_injector_v1.json`
- `trace_net_engineering_engram_prompt_retrieval_injector_v1_prompt_bundles.jsonl`
- quality-check JSON

Each prompt bundle contains selected retrieved atoms and a compact prompt guidance text block.

## Next module

H21 should wire this artifact into the engineering LLM prompt smoke as an optional prompt source, then compare against the prior fixed `--max-engram-atoms 4` path.
