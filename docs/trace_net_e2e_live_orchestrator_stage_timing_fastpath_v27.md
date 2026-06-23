# TRACE-Net E2E Live Orchestrator Stage Timing + Fast Path v27

Adds stage-level latency telemetry and a deterministic exact-query fast path on top of the v25 live orchestrator.

The fast path may skip the LLM only for strict exact lookups and audit-only exact misses. Source-truth evidence remains the only proof authority. Graph/Leiden, v2 summaries, and nearby context remain guidance only.

The endpoint does not scan raw 5TB data, rebuild graph artifacts, rerun OCR, mutate source truth, or write to external services.
