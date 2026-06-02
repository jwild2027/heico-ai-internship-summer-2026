# Visual text summary refresh from records

This patch adds a no-model repair command for the case where a long visual-text run
checkpointed `visual_text_extraction.jsonl`, corpus, and graph overlay files, but
crashed before writing the final summary JSON.

## Command

```bash
python scripts/refresh_visual_text_extraction_summary.py
```

It reads:

```text
local_data/organization/visual_text/visual_text_extraction.jsonl
```

and rewrites:

```text
local_data/organization/visual_text/visual_text_extraction_summary.json
local_data/organization/visual_text/visual_text_corpus.md
local_data/organization/visual_text/visual_text_graph_nodes.json
local_data/organization/visual_text/visual_text_graph_edges.json
```

No Ollama/model calls are made.
