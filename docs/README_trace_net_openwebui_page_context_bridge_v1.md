# TRACE-Net OpenWebUI Page Context Bridge v1

This bridge wires `page_context_pack_v3` into the current OpenWebUI/V3 answer path without replacing the existing Gemma bridge.

## Runtime shape

```text
Open WebUI
-> page-context proxy bridge on 8023
-> detects explicit page questions
-> builds page_context_pack_v3
-> injects source-bounded binder into OpenAI chat messages
-> forwards to existing V3 bridge on 8022
-> Gemma drafts from the binder
```

## Why this exists

TRACE-Net should not make Gemma a database. TRACE-Net builds the evidence binder. Gemma still thinks for complex questions, but it reasons inside source-trace limits.

The injected binder includes:

- selected page records
- source file/source link locators when available
- route-aware evidence priority
- route guidance and vector guidance
- per-page reasoning tasks
- proof/guidance counts
- safety constraints
- the global reasoning work order with `model_should_think: true`

## Safety contract

- Read-only artifact access.
- No source-truth mutation.
- No answer permission.
- No Postgres/Qdrant/OpenSearch writes.
- Vector, graph, visual, summary, and route guidance are not proof unless backed by source-trace proof records.
- Gemma may synthesize across evidence only when the evidence supports the claim.

## Open WebUI settings

After the proxy is running:

```text
Base URL: http://host.docker.internal:8023/v1
API Key: trace-net-local
Model: trace-net-page-context-v3-bridge
```

The proxy forwards to the current upstream V3 bridge by default:

```text
http://127.0.0.1:8022/v1
```

## Smoke questions

```text
write a paragraph about pages 48 and 202
What is on page 48?
What source file proves page 202?
```

Expected behavior: Gemma should explain what the page-context binder supports, separate proof from guidance, and avoid unsupported engineering authority claims.

## Runtime guardrail fallback

When the upstream V3 service is running in simulated mode, or when an upstream answer does not mention the requested page records, the page-context bridge can replace the off-topic response with a safe deterministic page-binder summary. This fallback is not a replacement for Gemma reasoning in Ollama mode. It exists to prevent simulated/off-topic answers from ignoring the page_context_pack_v3 binder during Open WebUI plumbing tests.

Fallback answers preserve the same safety boundary: no answer permission, no source-truth mutation, no DB writes, and no engineering overclaims without explicit source proof.

## Step 5C native page-binder answer mode

The bridge can now answer explicit page-context questions directly from `page_context_pack_v3` using a local Ollama/OpenAI-compatible chat endpoint before falling back to the upstream V27 exact-search path.

Default behavior for page questions:

1. detect page numbers from the OpenWebUI user question;
2. build the page-context binder;
3. send the binder directly to Gemma through Ollama;
4. require the native answer to mention the requested pages/page IDs;
5. return the native answer if aligned;
6. otherwise return the deterministic page-binder guardrail answer.

This keeps Gemma as a reasoning model for complex page questions while keeping all answers inside TRACE-Net proof limits. The model is allowed to synthesize cautiously, but graph/vector/visual/summary records remain guidance unless backed by proof. The bridge still sets no answer permission, performs no database writes, and does not mutate source truth.

Recommended local serve command:

```bash
python scripts/serve_trace_net_openwebui_page_context_bridge_v1.py \
  --host 127.0.0.1 \
  --port 8023 \
  --upstream-base-url http://127.0.0.1:8022/v1 \
  --model-id trace-net-page-context-v3-bridge \
  --upstream-model trace-net-e2e-live-orchestrator-fastpath-gemma-v27 \
  --native-page-answer-mode auto \
  --native-llm-base-url http://127.0.0.1:11434/v1 \
  --native-llm-model gemma4:26b \
  --native-request-timeout 300
```

Use `--native-page-answer-mode off` to disable the direct Gemma page-binder answerer and return to upstream-only proxy behavior.

## Native page-answer retry hardening

Native page-answer mode retries once with a stricter final-answer prompt if a thinking model returns an empty `message.content`. TRACE-Net records the empty-content diagnostic metadata, never exposes hidden reasoning/thinking text as the answer, and still requires page/page_id alignment before passing the model response. If retry output is still empty or unaligned, the bridge returns the safe page-context fallback.

## Native Ollama `/api/chat` final-content mode

For thinking models such as `gemma4:26b`, the OpenAI-compatible Ollama endpoint can spend the whole generation budget in a `reasoning` field and return empty `message.content`. TRACE-Net must not use hidden reasoning as the final answer. Native page-answer mode therefore calls Ollama's native `/api/chat` endpoint with `think: false`, a larger `num_ctx`, and a bounded `num_predict` so the user-visible final answer is emitted in `message.content`.

Additional serve options:

```bash
  --native-num-ctx 8192 \
  --native-max-tokens 1200
```

The response trace records `native_llm_provider_endpoint=ollama_api_chat`, the requested context window, and whether hidden reasoning/thinking fields were present. Alignment gates and fallback behavior remain unchanged.
