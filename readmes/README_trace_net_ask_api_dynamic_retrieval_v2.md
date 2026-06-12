# TRACE-Net Ask API Dynamic Retrieval v2

Read-only OpenAI-compatible API that dynamically builds TRACE-Net Hybrid Retrieval v2 groups for arbitrary queries while still requiring a final-gate artifact for final answers.

## Safety

- Dynamic retrieval groups are retrieval-only.
- Feedback, categories, and communities are advisory only.
- Final answer text is returned only when the existing final answer gate artifact authorizes the exact query.
- No Postgres, Qdrant, OpenSearch, graph, citation, or source writes occur.

## Build-only

```bash
python scripts/run_trace_net_ask_api_dynamic_retrieval_v2.py \
  --output-dir local_data/organization/trace_net/ask_api_dynamic_retrieval_v2 \
  --build-only \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_ask_api_dynamic_retrieval_v2_quality.py \
  --report-path local_data/organization/trace_net/ask_api_dynamic_retrieval_v2/trace_net_ask_api_dynamic_retrieval_v2.json \
  --require-dynamic-retrieval-available \
  --require-final-answer-quality-pass \
  --write-json
```

## Run server

```bash
python scripts/run_trace_net_ask_api_dynamic_retrieval_v2.py \
  --host 0.0.0.0 \
  --port 8013 \
  --output-dir local_data/organization/trace_net/ask_api_dynamic_retrieval_v2
```

## Open WebUI connection

Base URL:

```text
http://host.docker.internal:8013/v1
```

Model:

```text
trace-net-dynamic-hybrid-v2
```
