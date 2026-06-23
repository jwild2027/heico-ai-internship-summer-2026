# TRACE-Net E2E Live Eval + Latency Harness v26

Evaluates the live v25 orchestrator endpoint against a fixed regression set and records latency, false positives, false negatives, audit-only behavior, citation behavior, cap disclosures, and safety flags.

This stage does not mutate source truth, rebuild graph artifacts, rescan raw corpus data, rerun OCR, or write to retrieval services. It calls the already-running v25 endpoint and measures complete request latency.

Use this after v25 is running on `127.0.0.1:8021`.
