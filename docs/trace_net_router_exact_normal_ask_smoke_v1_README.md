# TRACE-Net Router Exact normal_ask Smoke v1

This benchmark complements the 50-question guided-discovery smoke. It verifies
that exact part-number lookup requests continue to route to the normal TRACE-Net
ask path through the OpenAI-compatible router endpoint.

## Adds

- `scripts/run_trace_net_router_exact_normal_ask_smoke_v1.py`
- `tests/fixtures/trace_net_router_exact_normal_ask_questions_v1.json`
- `tests/unit/test_trace_net_router_exact_normal_ask_smoke_v1.py`

## Contract

The benchmark checks:

- exact lookup route stays `normal_ask`
- `trace_net_payload` is present
- assistant content is clean text, not a raw JSON blob
- `final_answer_allowed` stays false
- source-truth mutation and write-attempt counters stay zero
- optional citation-backed minimum can be required with `--min-citation-backed-response-count`

It is read-only. It does not write to Postgres, Qdrant, or OpenSearch and does
not mutate source-truth artifacts.

## Example server run

```bash
python3 -B scripts/run_trace_net_router_exact_normal_ask_smoke_v1.py \
  --endpoint-url http://127.0.0.1:8017/v1/chat/completions \
  --model trace-net-router-proxy-v6 \
  --questions-file tests/fixtures/trace_net_router_exact_normal_ask_questions_v1.json \
  --output-dir /data/trace_net_runs/router_exact_normal_ask_smoke_v1 \
  --timeout-seconds 60 \
  --min-normal-ask-count 8
```

Add `--min-citation-backed-response-count 1` once at least one exact lookup is
expected to return citations in the active artifact set.
