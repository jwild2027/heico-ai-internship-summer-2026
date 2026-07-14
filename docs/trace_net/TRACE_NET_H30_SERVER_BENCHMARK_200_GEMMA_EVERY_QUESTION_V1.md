# TRACE-Net H30 200-Question Gemma-Every-Question Benchmark v1

## Purpose

This focused fix changes the 200-question server benchmark so every question
performs a real `gemma4:26b` call. The first ten conversational control prompts
no longer finish instantly without model inference.

## Per-question flow

1. Call the H30 full-stack endpoint on port 8128.
2. Preserve the production TRACE-Net safe draft and all fail-closed metadata.
3. Call Ollama `gemma4:26b` through `/api/chat` for a bounded answer-render pass.
4. Validate the Gemma answer against identifiers, citations, evidence class,
   authority boundaries, and follow-up duplication.
5. Use the Gemma answer only when validation passes; otherwise retain the
   production safe draft and mark the benchmark question failed.
6. Write a checkpoint after the question completes.

Progress prints four visible stages per question:

```text
[001/200] START ...
[001/200] TRACE_NET_DONE ...
[001/200] GEMMA_START model=gemma4:26b
[001/200] GEMMA_DONE ...
[001/200] PASS ...
```

## Output

Each JSON record includes `trace_net_safe_answer`, the final `answer`,
`benchmark_gemma_answer`, follow-up questions, model metadata, Gemma timing,
Gemma validation, route, tunnels, evidence counts, Self-RAG, CRAG, production
writer status, and all fail-closed flags.

## Safety

The benchmark remains read-only. It does not write PostgreSQL, Qdrant,
OpenSearch, source-truth artifacts, or generated repository data. Production
safety behavior is not loosened. Candidate/visual/semantic/graph/summary
results remain guidance-only, and authority-sensitive claims require explicit
authority evidence.
