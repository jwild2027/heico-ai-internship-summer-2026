# TRACE-Net Ask CLI v1

Runs the safe deterministic retrieval/answer path in one command:

```text
search -> source citations -> grouped page results -> answer composer
```

It uses only existing TRACE-Net safe candidate/index artifacts. It does not call an LLM, create embeddings, or read excluded raw extraction records.

## Usage

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
  --top-k 10 \
  --open
```

Exact page lookup:

```bash
python scripts/trace_net_ask.py \
  --page-id t_p_120_1176_p000010 \
  --top-k 10 \
  --open
```

Quality gate:

```bash
python scripts/check_trace_net_ask_quality.py \
  --write-json \
  --min-answer-pages 1 \
  --min-evidence-records 1 \
  --max-unsafe-answer-groups 0
```

Outputs:

```text
local_data/organization/trace_net/ask/trace_net_ask_summary.json
local_data/organization/trace_net/ask/trace_net_ask_stages.jsonl
local_data/organization/trace_net/ask/trace_net_ask_report.md
local_data/organization/trace_net/ask/trace_net_ask_report.html
```

The final answer artifacts remain in:

```text
local_data/organization/trace_net/answers/
```
