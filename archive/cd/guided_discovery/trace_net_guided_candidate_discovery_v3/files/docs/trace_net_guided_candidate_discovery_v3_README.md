# TRACE-Net Guided Candidate Discovery v3

Adds stricter candidate-token hygiene on top of guided candidate discovery v2.

## Purpose

Low-context/partial part lookup should return possible routes and clarifying questions, not a final answer. v3 keeps strict prefix and loose candidate groups from v2, but filters noisy OCR/artifact tokens before they become user-facing candidate routes.

## Key behavior

- Separates strict prefix matches from weaker related candidates.
- Rejects decimal OCR noise like `24.689877` and `2424.0`.
- Rejects hash/graph-id-like tokens.
- Keeps plain short numeric tokens out of primary routes unless they have strong part context.
- Prefers structured aviation-like identifiers such as `120-48024-001`, `MS24693-C5`, `PE21052-2`, and similar shapes.
- Adds `candidate_quality`, `rejected_noise_token_count`, and `weak_token_count` for debugging.
- Avoids polluted V2/V3 summaries from query-plan/answer-context artifacts.

## Safety contract

- Read-only local artifact scan.
- No Postgres, Qdrant, or OpenSearch writes.
- No source-truth mutation.
- `final_answer_allowed=false` for discovery routes.

## Example

```bash
PYTHONUNBUFFERED=1 python3 -u scripts/run_trace_net_guided_candidate_discovery_v3.py \
  --artifact-root local_data/organization/trace_net \
  --output-dir /data/trace_net_runs/guided_candidate_discovery_v3 \
  --question "I am looking for a part that starts with numbers 2 and 4 but I do not have the rest" \
  --top-k 8 \
  --loose-top-k 8
```
