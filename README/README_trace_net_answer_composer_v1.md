# TRACE-Net Answer Composer v1

This patch adds a deterministic answer composer for grouped TRACE-Net search results.

It reads page-level grouped search results from:

```text
local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
```

and writes a source-backed answer draft under:

```text
local_data/organization/trace_net/answers/
```

Outputs:

```text
trace_net_answer_draft.json
trace_net_answer_draft.md
trace_net_answer_draft.html
trace_net_answer_evidence.jsonl
trace_net_answer_summary.json
trace_net_answer_graph_nodes.json
trace_net_answer_graph_edges.json
trace_net_answer_quality.json
```

The answer composer is deterministic. It does not call an LLM, create embeddings, or read excluded/raw extraction records. It only summarizes safe grouped search results and their source metadata.

## Run

Run a search and grouping first, then:

```bash
python scripts/compose_trace_net_answer.py --open
```

## Quality

```bash
python scripts/check_trace_net_answer_quality.py \
  --write-json \
  --min-pages 1 \
  --min-evidence-records 1 \
  --min-citation-groups 1 \
  --max-unsafe-groups 0 \
  --max-missing-source-url-groups 0 \
  --max-missing-tiff-path-groups 0 \
  --max-missing-ocr-path-groups 0
```

## Architecture position

```text
Local Search Harness
  -> Search Result Grouper
  -> Answer Composer v1
  -> Source-backed answer draft
```
