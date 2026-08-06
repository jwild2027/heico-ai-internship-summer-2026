# TRACE-Net router proxy v6.1 q044 policy fix

This patch targets the single remaining v6 full 50-question WARN: q044 routed to `normal_ask` instead of guided clarification.

It adds a narrow shim for loose-contains/exact-match policy wording and a focused unit test file.
