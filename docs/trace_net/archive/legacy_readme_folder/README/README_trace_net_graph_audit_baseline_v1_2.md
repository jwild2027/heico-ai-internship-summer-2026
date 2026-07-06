# TRACE-Net Graph Audit/Baseline v1.2

Fixes two graph-audit issues found during Postgres testing:

1. Avoids psycopg `%` placeholder parsing errors by replacing SQL `LIKE '%' || ... || '%'` checks with `position(...) > 0` checks.
2. Treats OCR export page IDs such as `zip_page_000003` and TRACE-Net canonical page IDs such as `t_p_120_1176_p000003` as aliases by matching page numbers.

This is still read-only. It does not mutate the graph, source truth, trust tiers, RAG eligibility, or ranking.
