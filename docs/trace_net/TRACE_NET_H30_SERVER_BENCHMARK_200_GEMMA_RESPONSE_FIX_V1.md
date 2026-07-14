# TRACE-Net H30 200-Question Gemma Response Fix V1

## Problem

The 200-question benchmark made real `gemma4:26b` calls, but the adapter only read
`message.content`. On thinking-capable Ollama models, successful HTTP 200 responses
can expose output through a different response field, leaving `message.content`
empty. The benchmark then reported `gemma_empty_answer` even though inference ran.

## Fix

- Send `think: false` for deterministic structured JSON rendering.
- Parse `message.content` first, then guarded compatible fields.
- Retry once only when the response is empty or malformed.
- Record response shape diagnostics without weakening answer validation.
- Run three real structured-output probes before question 1.
- Refuse to start the 200-question benchmark when any probe fails.
- Use a fresh runtime/checkpoint directory.

## Safety

The patch is read-only and preserves:

- `answer_permission=false`
- `final_answer_allowed=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`

It does not write PostgreSQL, Qdrant, OpenSearch, or source-truth artifacts.
Candidate, visual, graph, semantic, and summary results remain guidance only.
Authority-sensitive claims still require explicit authority evidence.

## Expected progress

Before question 1:

```text
GEMMA_STRUCTURED_OUTPUT_PREFLIGHT=PASS probes=3/3 think=false
```

Per question:

```text
[001/200] GEMMA_START model=gemma4:26b
[001/200] GEMMA_DONE status=200 ... source=message.content attempts=1 think=false
```
