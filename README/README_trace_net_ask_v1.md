# TRACE-Net Ask Pipeline v1

Runs the deterministic TRACE-Net answer pipeline in one command:

```text
search -> source citations -> grouped results -> answer composer
```

This script does not call an LLM, generate embeddings, or read excluded/raw extraction records. It orchestrates existing, quality-gated TRACE-Net scripts.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_ask.py \
  tests/unit/test_tiff_trace_net_ask_cli.py \
  -q
```

## Example usage

Part lookup:

```bash
python scripts/trace_net_ask.py \
  --part-number 120-50645-009 \
  --top-k 10 \
  --open
```

Natural-language query:

```bash
python scripts/trace_net_ask.py \
  --query "seat bottom backrest" \
  --bucket source_text_evidence,derived_context \
  --top-k 10 \
  --open
```

Page lookup:

```bash
python scripts/trace_net_ask.py \
  --page-id t_p_120_1176_p000010 \
  --top-k 10 \
  --open
```

Optional downstream quality gates:

```bash
python scripts/trace_net_ask.py \
  --part-number 120-50645-009 \
  --top-k 10 \
  --run-quality \
  --open
```

## Outputs

```text
local_data/organization/trace_net/ask/trace_net_ask_summary.json
local_data/organization/trace_net/ask/trace_net_ask_report.md
local_data/organization/trace_net/ask/trace_net_ask_report.html
```

The existing downstream artifacts are also refreshed:

```text
local_data/organization/trace_net/search/trace_net_search_results.jsonl
local_data/organization/trace_net/citations/trace_net_search_results_with_citations.jsonl
local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
local_data/organization/trace_net/answers/trace_net_answer_draft.md
```
