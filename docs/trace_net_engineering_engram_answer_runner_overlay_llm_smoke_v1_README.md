# TRACE-Net Engineering Engram Answer-Runner Overlay LLM Smoke v1

H25 performs a targeted smoke for retrieved Engram overlays against saved
engineering answer-runner prompts.

It is designed to avoid another full 30-question Gemma run. The default target
set is:

- q12 interchangeability boundary
- q16 visual/OCR route explanation
- q18 pipeline recovery / safe-but-too-generic repair
- q25 unknown part / no proof context
- q29 summary-only proof limit

## Safety contract

- No Postgres writes
- No Qdrant reads/writes
- No OpenSearch writes/uploads
- No source-truth mutation
- No answer permission
- Retrieved Engram overlays are behavior guidance only and never source proof

## Modes

- `artifact`: deterministic scaffold, no LLM call
- `ollama`: short targeted local Gemma smoke

## Expected usage

Run tests, then build artifact mode, then run the short Ollama mode only after
artifact mode passes.
