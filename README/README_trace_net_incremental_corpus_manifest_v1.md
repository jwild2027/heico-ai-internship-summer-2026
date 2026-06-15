# TRACE-Net Incremental Corpus Manifest v1

Step 24 builds a read-only, dependency-aware manifest for new/changed corpus arrivals.
It is the bridge between the current TIFF incrementer and the future 5 TB corporate
pipeline.

The manifest answers:

```text
What source files exist?
Which files are new, changed, unchanged, or removed?
Which pages are affected?
Which downstream stages are dirty?
Which pages need OCR/table/visual/embedding/Qdrant/OpenSearch/graph/Leiden refresh?
```

It does not mutate Postgres, Qdrant, OpenSearch, the graph, source files, trust, or
source truth. It is a planner only.

## Core rule

```text
New/changed file -> affected pages -> dirty stages -> incremental work plan.
```

Not:

```text
New/changed file -> rescan the whole corpus.
```

## Build command

```bash
python scripts/build_trace_net_incremental_corpus_manifest_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --element-graph-attachment local_data/organization/trace_net/element_graph_attachment/trace_net_element_graph_attachment_plan_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --feedback-memory local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --source-root local_data/sample_tiffs \
  --source-root local_data/rescarta_toolkit_input/t_p_120_1176_pages \
  --output-dir local_data/organization/trace_net/incremental_corpus_manifest \
  --fingerprint-mode stat \
  --require-page-count 509 \
  --quality
```

Use `--fingerprint-mode sha256` for stronger but slower content hashing.

## Previous manifest comparison

```bash
python scripts/build_trace_net_incremental_corpus_manifest_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --previous-manifest local_data/organization/trace_net/incremental_corpus_manifest/trace_net_incremental_corpus_manifest_v1.json \
  --source-root local_data/sample_tiffs \
  --output-dir local_data/organization/trace_net/incremental_corpus_manifest_next \
  --require-page-count 509 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_incremental_corpus_manifest_v1_quality.py \
  --report-path local_data/organization/trace_net/incremental_corpus_manifest/trace_net_incremental_corpus_manifest_v1.json \
  --require-page-count 509 \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/incremental_corpus_manifest/
  trace_net_incremental_corpus_manifest_v1.json
  trace_net_incremental_corpus_manifest_v1_sources.jsonl
  trace_net_incremental_corpus_manifest_v1_pages.jsonl
  trace_net_incremental_corpus_manifest_v1_dirty_pages.jsonl
  trace_net_incremental_corpus_manifest_v1_summary.json
  trace_net_incremental_corpus_manifest_v1_quality.json
  trace_net_incremental_corpus_manifest_v1.md
```

## Safety fields

Every source/page manifest record is explicitly:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
```

The manifest can guide incremental processing. It cannot prove or answer anything.
