# TRACE-Net Engineering Engram Memory Layers v1

H17 formalizes the TRACE-Net Engram as a typed engineering memory taxonomy.  The goal is not to make the LLM human or to add source facts to memory.  The goal is to make behavior memory explicit, inspectable, versioned, and testable.

## Memory layers

| Layer | Meaning | Runtime role |
| --- | --- | --- |
| `working_memory` | Current question, current context pack, current proof citations | Temporary answer-time state |
| `semantic_memory` | Stable route/evidence meaning, such as visual link vs OCR nomenclature | Route meaning guidance |
| `procedural_memory` | If/then behavior rules, such as no interchangeability without authority | Answer boundary control |
| `episodic_memory` | Past runs, smoke failures, fixes, and regression lessons | Failure recall and regression prevention |
| `trait_memory` | Cautious, source-trace-first, helpful-but-not-overclaiming behavior profile | Consistent engineering style |
| `critic_memory` | Self-RAG/CRAG critique and repair lessons | Draft critique and repair |

## Proof boundary

Engram memory is behavior guidance only.  It can guide how TRACE-Net plans, phrases, critiques, and repairs answers.  It cannot prove source facts, mutate source truth, or grant answer permission.  Manual facts must still come from current `proof_context` citations.

`working_memory` is the only layer that can carry current proof citations, and only as temporary answer-time state.  This artifact does not persist manual source truth.

## Safety contract

`no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission`

H17 is artifact-only.  It does not write to Postgres, Qdrant, OpenSearch, or any source-truth store.

## Build

```bash
python -B scripts/build_trace_net_engineering_engram_memory_layers_v1.py \
  --engram-core local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json \
  --output-dir local_data/organization/trace_net/engineering_engram_memory_layers_v1 \
  --min-atoms 6 \
  --max-unsafe 0
```

## Check

```bash
python -B scripts/check_trace_net_engineering_engram_memory_layers_v1.py \
  --memory-layers local_data/organization/trace_net/engineering_engram_memory_layers_v1/trace_net_engineering_engram_memory_layers_v1.json \
  --min-atoms 6 \
  --require-all-layers \
  --require-quality-pass \
  --require-no-answer-permission \
  --max-unsafe 0 \
  --max-write-attempts 0
```

## Next

H18 can load the active, guidance-only Engram atoms into Qdrant for semantic retrieval.  H19 can use retrieved memory layers in a Self-RAG critic.  H20 can use critic/episodic/procedural atoms for CRAG repair.
