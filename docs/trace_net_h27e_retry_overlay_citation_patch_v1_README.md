# TRACE-Net H27E Retry Overlay Citation Patch v1

H27E is a narrow repair for the H27 real answer-smoke overlay path.

## Problem

The H27 targeted real answer-smoke proved that the H24 overlay is injected into saved prompts, but q18 fell into the minimal retry path. The retry answer was safe and cited grouped labels such as `[V6, V7, V8]`, but the smoke citation counter expects individual labels like `[V6] [V7] [V8]`, so the answer was graded PARTIAL.

## Fix

- Keep H27 overlay wiring.
- Append a narrow citation syntax instruction to the full prompt.
- Apply the same Engram overlay and citation syntax instruction to the retry prompt.
- Do not alter proof contexts, source-truth artifacts, DBs, Qdrant, or OpenSearch.

## Safety contract

Artifact/prompt-only repair. No answer permission, no source-truth mutation, no live Qdrant/Postgres/OpenSearch writes.
