# TRACE-Net Engineering Engram Prompt Injector Reliability v1

H16B hardens the H16 Engram prompt injection layer.

## Why

The first H16 run proved that Engram atoms were being injected, but a few local Ollama calls returned empty output on long/complex prompts. The safety counters stayed clean, but the smoke test blocked because no answer text was returned.

## What changed

- Engram atoms are compacted before prompt injection.
- If the full prompt fails or Ollama returns no answer text, the runner retries once with a minimal prompt that keeps proof context and scaffold but removes Engram bulk.
- If the retry also fails, the runner writes a conservative TRACE-Net scaffold fallback answer so the result is safe, inspectable, and non-empty.
- Safe reasoning traces record retry/fallback status.
- Engram memory remains behavior guidance only and is never source proof.

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes/uploads.
- No source-truth mutation.
- No answer permission granted.
- Fallback answers still use proof_context citations when proof exists and say not source-trace-ready when it does not.
