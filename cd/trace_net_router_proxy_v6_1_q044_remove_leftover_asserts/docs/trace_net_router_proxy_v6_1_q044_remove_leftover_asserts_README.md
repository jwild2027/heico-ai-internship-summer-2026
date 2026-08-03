# TRACE-Net Router Proxy v6.1 q044 leftover safety assert cleanup

This is a test-only cleanup for the q044 routing-policy regression test.

The q044 router behavior was already correct after the policy fix:

- route is `guided_discovery`
- `fast_clarification_only` is `true`
- endpoint is `internal://trace-net/router/fast-clarification`
- final answer remains blocked

The failing assertion was a stale test expectation that read `postgres_write_attempt_count` directly from the top-level response. Fast-clarification payloads keep safety counters under `safety_contract`, so the test should use the fallback-safe assertions already added.

No router behavior is changed by this cleanup.
