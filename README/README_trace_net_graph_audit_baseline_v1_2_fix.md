# TRACE-Net Graph Audit Baseline v1.2 Fix

Fixes two issues in the Postgres graph audit:

1. Escapes SQL wildcard percent signs so psycopg does not treat `%` as an invalid placeholder.
2. Makes page-link checks alias-aware. OCR-loaded pages may use `zip_page_000003` while TRACE-Net evidence uses `t_p_120_1176_p000003`; the audit now treats `document_id + page_number` aliases as valid page links.

This is read-only. It does not mutate Postgres data.
