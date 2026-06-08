# TRACE-Net Graph Audit + Pre-Algorithm Baseline v1

Read-only checkpoint before applying a new algorithm filter/ranking mode.

## Modules

- `audit_trace_net_postgres_graph.py`: traverses/checks the Postgres graph and linkage quality.
- `build_trace_net_pre_algorithm_baseline.py`: captures baseline counts/metrics before algorithm changes.
- quality gates for both outputs.

No script mutates source truth, ranking, RAG eligibility, feedback, or trust tiers.
