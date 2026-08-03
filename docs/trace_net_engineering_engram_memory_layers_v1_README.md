# TRACE-Net Engineering Engram Memory Layers v1

H17 defines the six TRACE-Net Engram memory layers. Phase 2 of the
non-redundancy work clarifies an important boundary:

- `working_memory` exists only during the current request;
- the committed JSON artifact stores only long-lived behavior and experience;
- source facts still come only from the current evidence and citations.

## Memory layers

| Layer | Meaning | Storage |
| --- | --- | --- |
| `working_memory` | Current question, claims, searches, evidence, rejected evidence, best result, unresolved fields, repair budget | Runtime only |
| `semantic_memory` | Stable meaning of visual, OCR, table, graph, summary, and citation evidence | Persisted guidance |
| `procedural_memory` | Reusable if/then behavior and safety boundaries | Persisted guidance |
| `episodic_memory` | Past failures, repairs, tests, and planner examples | Persisted guidance |
| `trait_memory` | Stable engineering style and answer behavior | Persisted guidance |
| `critic_memory` | Self-RAG and CRAG critique/repair lessons | Persisted guidance |

## Taxonomy cleanup

The builder now:

- uses the readable `engram_id` already stored in the Engram core;
- keeps former `h17_imported_<hash>` IDs under `legacy_atom_ids`;
- preserves `good_behavior` as `allowed_behavior`;
- preserves `bad_behavior` as `forbidden_behavior`;
- maps each core memory type to the correct layer;
- rejects static persisted `working_memory` atoms;
- treats saved query-planner examples as episodic memory.

## Proof boundary

Engram memory is behavior guidance only. It can guide planning, phrasing,
criticism, and repair. It cannot prove source facts, mutate source truth, or
grant answer permission.

The request-local working-memory object may temporarily point to current
citations, but it is never persisted as manual source truth.

## Safety contract

`no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission`

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

`--require-all-layers` requires every persisted layer. Working memory is
validated separately as runtime-only and therefore has a committed count of 0.
