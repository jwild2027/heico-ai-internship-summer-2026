# TRACE-Net Strict Query Planning and Gemma Telemetry v1

This patch fixes two false-positive retrieval paths found by the 180-question
server benchmark.

## Fixes

- `Search ATA 98-98-98` is treated as a strict manual-reference lookup.
- Natural IPL/table queries extract a strict target, including:
  - `Search the IPL table for RING, LOCKING`
  - `Find locking ring in the illustrated parts list`
  - `Find the IPL row for NONEXISTENT COMPONENT`
- Unresolved dynamic questions no longer promote every indexed field to direct
  proof.
- Unknown or unresolved targets fail closed with audit-only/no-evidence output.

## Gemma telemetry

The benchmark now reports whether each retrieval check:

- called Gemma successfully;
- skipped Gemma through the deterministic exact fast path;
- failed the Gemma call;
- and how long the request took.

Use:

```bash
--llm-mode ollama --fast-path-mode off --require-gemma-call
```

to require a successful Gemma call for all manifest retrieval checks.

The 155 router/follow-up-only records remain deterministic and fast. A separate
full unified-endpoint benchmark is required to exercise all 180 questions
through the complete API route.
