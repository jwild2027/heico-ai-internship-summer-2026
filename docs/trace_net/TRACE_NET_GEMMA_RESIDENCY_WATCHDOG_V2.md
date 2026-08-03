# TRACE-Net Gemma Residency Watchdog v2

## Purpose

The measured public endpoint was healthy while Ollama had no resident models.
The first question therefore loaded `gemma4:26b` inside the user request and took
about 128.6 seconds, versus an 18.2-second warm median.

This patch separates model availability from residency and prevents the public
stack from declaring itself ready until Gemma is actually resident.

## Changes

1. `trace_net_h30_gemma_residency_watchdog_v2.py`
   - checks `/api/tags` for model availability;
   - checks `/api/ps` for actual residency;
   - preloads through `/api/generate` with an empty prompt and configured
     `keep_alive`;
   - renews residency before the expiry window;
   - recovers from unexpected eviction before an answer-writing request;
   - reports preload/check counters and timing;
   - performs no retrieval, evidence selection, source mutation, or DB writes.

2. `serve_trace_net_nha_phase16_gemma_proxy_v1_1.py`
   - preserves the existing NHA packet, Engram, evidence, Self-RAG, and fallback
     behavior;
   - requires resident Gemma on startup;
   - emits safe `trace_net.progress` SSE events with no assistant answer content;
   - releases the final answer only after the existing validation path finishes;
   - records packet, residency, upstream, model, and total timing.

3. `launch_trace_net_gemma_resident_openwebui_v2.sh`
   - verifies port 8118;
   - preloads and verifies Gemma;
   - restarts only 8128 and 8131;
   - gates both health endpoints on actual residency;
   - verifies safe progress streaming.

## Health contract

The patched health output distinguishes:

- `gemma_model_available`: the model is installed in Ollama;
- `gemma_model_resident`: the model is currently in `/api/ps`;
- `cold_start_risk`: the model is not resident;
- `gemma_residency_watchdog_running`: the renewal thread is active.

With `TRACE_NET_GEMMA_REQUIRE_RESIDENT=1`, `quality_status=PASS` requires actual
residency.

## Defaults

```text
TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_ENABLED=1
TRACE_NET_GEMMA_REQUIRE_RESIDENT=1
TRACE_NET_GEMMA_KEEP_ALIVE=1h
TRACE_NET_GEMMA_RESIDENCY_CHECK_INTERVAL_SECONDS=300
TRACE_NET_GEMMA_RENEW_BEFORE_SECONDS=900
TRACE_NET_GEMMA_PRELOAD_TIMEOUT_SECONDS=300
```

## Safety contract

The patch keeps all of these false/zero:

```text
answer_permission=false
source_truth_mutation_allowed=false
postgres_write_attempt_count=0
qdrant_write_attempt_count=0
opensearch_write_attempt_count=0
```

Progress events contain no OpenAI `choices` field and no model-generated answer
content. Clients may ignore them without affecting the final answer.

## Same-question verification

After deployment, run:

```bash
python -u -B scripts/run_trace_net_gemma_residency_same10_v2.py \
  --base-url http://172.17.0.1:8131 \
  --api-key trace-net-openwebui-cognitive \
  --model trace-net-gemma4-cognitive-rag-v1 \
  --count 10 \
  --require-progress \
  --output-dir /data/trace_net_runs/gemma_residency_same10_v2
```

The test requires Gemma to be resident before Question 1 and compares the first
request with the median of Questions 2–10 using the identical prompt.
