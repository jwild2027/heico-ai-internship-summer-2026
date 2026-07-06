# TRACE-Net Engineering Engram Postgres Feedback Ledger v1

H31 creates an artifact-first feedback ledger for TRACE-Net Engram memory.

It turns answer-smoke, Self-RAG critic, CRAG repair, and optional user feedback JSONL into:

- `trace_net_engineering_engram_feedback_ledger_schema_v1.sql`
- `trace_net_engineering_engram_feedback_ledger_records_v1.jsonl`
- `trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl`
- `trace_net_engineering_engram_postgres_feedback_ledger_v1.json`

Safety boundary:

- Feedback is behavior guidance only.
- Feedback is not proof_context.
- Feedback cannot grant answer permission.
- Feedback cannot mutate source truth.
- Live Postgres writes are disabled unless an explicit future executor/gate is used.

This patch intentionally emits SQL and JSONL artifacts first. It does not perform live database writes by default.
