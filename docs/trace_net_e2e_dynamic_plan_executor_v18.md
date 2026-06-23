# TRACE-Net E2E Dynamic Plan Executor v18

This phase executes validated v17 query plans against prebuilt source-truth evidence and graph/summary guidance artifacts.

It is designed for large corpora where query time must not scan raw source files. The graph is assumed to be built offline. Query time uses bounded, typed graph guidance and Leiden community metadata only after source-truth seed evidence is found.

## Authority model

- Source-truth exact evidence can support final claims.
- Leiden/community graph guidance can propose related neighborhoods but cannot prove a claim.
- v2 summaries can compress/explain candidate pages but cannot prove a claim.
- High-degree entities use aggregation plus capped samples rather than silent truncation.
- Capped results disclose total and returned counts.

## Output

The report contains source-truth evidence records, graph guidance, summary guidance, route guidance, aggregation counts, capped-result metadata, and a graph policy contract for downstream context packs.
