# TRACE-Net NHA N14–N16 Cognitive Integration v1

This package connects the reviewed N13 NHA atoms and skill cards to the promoted
real N4 relationship bundle and adds one constrained Gemma answer-only call.

## Runtime contract

1. N13 extracts deterministic NHA atoms and selects exactly one reviewed NHA skill.
2. The N6 real-source relationship engine retrieves the supported relationship facts.
3. N14 builds a compact evidence packet and selects relevant NHA memory atoms.
4. N15 sends one JSON-constrained answer-only request to `gemma4:26b` through Ollama.
5. N16 validates identifiers, ambiguity language, and the public contract.
6. Evidence and Limits remain deterministic. Any model failure falls back to the
   already-valid deterministic answer after exactly one attempted Gemma call.

Engram guidance is never evidence. Synthetic N5 artifacts are never loaded.

## New model

- Base URL: `http://172.17.0.1:8132/v1`
- API key: `trace-net-openwebui-cognitive`
- Model: `trace-net-gemma4-cognitive-rag-nha-engram-v1`

## Live gate

The N16 server gate runs:

- N13 and N14–N16 unit tests
- shadow connection validation with zero NHA Gemma calls
- gated 20-question live benchmark
- 18 Engram-guided NHA Gemma answers
- one ordinary upstream passthrough control
- one synthetic safe-block control
- ten streaming and ten non-streaming requests

A strict PASS requires all 18 NHA answers to be accepted from Gemma with no
fallback, one NHA Gemma call per answer, Engram skill and atom telemetry present,
and Self-RAG/public-contract validation passing.
