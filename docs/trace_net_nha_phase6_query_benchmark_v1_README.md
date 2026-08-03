# TRACE-Net NHA Phase N6 Query Benchmark v1

N6 adds a deterministic, read-only NHA query engine over:

- N4 real-source hierarchy relationships.
- N5 synthetic benchmark relationships, only when explicitly enabled.

Supported operations include direct NHA, ancestor chain, direct children,
descendants, project/revision comparison, conflict-limited answers, evidence-page
lookup, and no-NHA negative controls.

Safety contract:

- No LLM calls.
- No TIFF or OCR modification.
- No Phase N4/N5 artifact mutation.
- No Postgres, Qdrant, OpenSearch, or production graph writes.
- Synthetic answers are always labeled benchmark-only.
- Synthetic evidence cannot support production claims.
