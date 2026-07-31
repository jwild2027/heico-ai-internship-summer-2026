# TRACE-Net NHA Blue-Green Final Gate v1

This milestone removes live-stack rebuilds from candidate testing and future promotion.

## Runtime layout

Production stays live while an inactive candidate runs:

- Current public front door: `8131`
- Existing shared retrieval upstreams: `8117`, `8116`
- Green candidate: router `8218`, writer `8228`, NHA `8231`, benchmark `8233`
- Blue candidate: router `8318`, writer `8328`, NHA `8331`, benchmark `8333`

The first successful run installs `serve_trace_net_blue_green_frontdoor_v1.py` on `8131`. The front door reads an atomic JSON pointer from:

`/data/trace_net_runs/blue_green_frontdoor_v1/active_backend.json`

Later promotions update this pointer with `os.replace()` after candidate health and acceptance gates pass. They do not restart `8118`, `8128`, or `8131`.

## Failure behavior

Before promotion, a failure stops only the inactive candidate color and its isolated benchmark port. Production ports and the active pointer are not changed. There is no production rollback handler.

## Acceptance

The candidate must pass:

1. Focused unit and legacy writer-isolation tests.
2. Candidate health with Phase 19 route completion and preservation writer enabled.
3. The proven mixed 12-query real-model gate against the candidate NHA endpoint.
4. The isolated 100-query next-highest-assembly benchmark with exactly 100 real Gemma calls and 100 answer-key matches.
5. Candidate manifest validation.
6. Atomic pointer promotion.
7. Public `8131` real-NHA and synthetic-block smoke checks.

Production synthetic identifiers remain blocked. The 100-query answer key is loaded only by the isolated benchmark service.
