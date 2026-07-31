# TRACE-Net N20 final NHA + Gemma100 benchmark

This patch finishes the incomplete N19 promotion and adds the final NHA acceptance gate.

## N19 completion

The cognitive launcher now runs its legacy unit-test suite with the Phase 19
preservation-writer environment disabled. This prevents a deployment environment
value (`384` generation tokens) from contaminating the older base-writer test that
intentionally verifies the original `512` token contract. The real 8118/8128
processes still start with N19 enabled after tests pass.

## Real-Gemma 100-question benchmark

The N20 benchmark derives 100 unique natural-language direct-NHA questions from
a tracked compact answer key generated from the canonical Phase 5 synthetic seed.
The key contains the 50 confirmed relationships with exactly one global parent
per child, so the server does not depend on untracked local_data. It uses 50 globally unambiguous
synthetic child-parent pairs and at least 20 wording templates. Fifty requests are
streaming and fifty are non-streaming.

Every request:

1. Uses the normal public model id `trace-net-gemma4-cognitive-rag-v1` through an OpenAI-compatible `/v1/chat/completions` call.
2. Is recognized as a normal direct-NHA question.
3. Retrieves the deterministic benchmark-only synthetic parent relationship.
4. Calls real `gemma4:26b` exactly once.
5. Requires a validator-accepted Gemma answer; deterministic fallback never counts.
6. Compares the answer to the Phase 5 synthetic answer key.

## Isolation

Production `8131` continues blocking reserved `990-` synthetic identifiers. The
benchmark runs temporarily on localhost port `8133`, stops after the test, and
never writes source truth, Postgres, Qdrant, OpenSearch, the production graph, TIFF,
or OCR artifacts.

## Strict PASS

- 100 questions
- 100 unique prompts
- 100 HTTP 200 responses
- 100 real Gemma calls
- 100 validator-accepted Gemma answers
- 100 answer-key matches
- 0 deterministic fallbacks
- 50 streaming / 50 non-streaming
- at least 40 distinct synthetic relationships
- at least 20 wording templates
- 0 production synthetic access
- 0 production graph writes
- 0 source mutations
