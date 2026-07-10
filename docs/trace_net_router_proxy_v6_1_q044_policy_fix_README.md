# TRACE-Net router proxy v6.1 q044 policy fix

This patch is a narrow benchmark repair for the remaining v6 full 50-question WARN.

## Problem

`q044` asks:

```text
I want to know if a loose contains match should be treated as exact.
```

The question has no digits and no part noun, so v6 routed it to `normal_ask`. The 50-question discovery smoke expects this routing-policy question to ask clarifying/source-trace questions before treating a loose contains candidate as exact.

## Fix

The patch appends a small v6.1 shim before the script entrypoint in:

```text
scripts/serve_trace_net_guided_discovery_router_proxy_v6.py
```

It preserves the public model name `trace-net-router-proxy-v6` and overrides only:

- `should_fast_clarify`
- `build_fast_clarification_questions`

for loose-contains/exact-policy wording.

## Safety contract

No source artifacts are mutated. No writes are attempted to Postgres, Qdrant, or OpenSearch. Final answer permission remains false. Guided discovery remains candidate-discovery-only.
