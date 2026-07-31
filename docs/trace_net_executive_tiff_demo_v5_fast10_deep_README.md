# TRACE-Net Executive TIFF Demo v5.1 — Deep Fast10

This is a separate presentation mode for a short executive demonstration. It does not replace v2, v3, or the corrected full-corpus v4.1 mode.

## v5.1 focused fix

The original v5 run found nine fully validated routes and one conservative validator-gated page:

- page: `t_p_120_1176_p000341`
- source route: `table`
- retry score: `55`
- retrieval threshold: not met

The page was not actually unknown. The full 509-page classification also identifies page 341 as a table/IPL page. v5.1 therefore keeps its visible document type as `TABLE / ILLUSTRATED PARTS LIST` while preserving the conservative safety hold.

The safety hold means:

- the page stays in the graph;
- its original TIFF and lineage remain visible;
- it is not embedded;
- it is not sent to exact search;
- it cannot act as direct answer evidence;
- the production classifier thresholds are not weakened.

## Default source window

The demo copies original TIFF pages 339 through 348 into a temporary ten-page ZIP. That window includes the evidence area around pages 342–344 used by the included part and next-higher-assembly example questions.

## Visible chronology

1. Print the ten original source pages selected.
2. Run OCR and print `OCR PROGRESS 01/10` through `10/10`.
3. Execute all nine build stages and their nine quality checks.
4. Print the OCR result for every page.
5. Print exactly one visible page class per page.
6. Mark any low-confidence page as `GRAPH-ONLY SAFETY HOLD` rather than `UNKNOWN`.
7. Print `GRAPH NODES MADE` and `GRAPH EDGES MADE`.
8. Print the six Engram layers.
9. Run BGE-M3 for validated searchable pages and visibly skip safety-hold pages.
10. Ask two example questions.
11. Print deterministic query atoms, route choice, bounded tunnels, retrieval evidence, evidence envelope, Engram update, one Gemma call, and final validators.
12. Print the final cited answer and safety summary.

## Classification contract

The final presentation gate requires:

- expected page count: 10
- visible classified page count: 10
- unknown page count: 0
- duplicate page ID count: 0
- fully validated retrieval routes: at least 9
- validator-gated graph-only routes: at most 1
- graph-ready records: 10

Only these four visible page classes are allowed:

- blank / nearly blank
- normal text / procedure
- table / illustrated parts list
- image / diagram

## Safety

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- graph-only pages are not embedded or exact-indexed
- original 509-page ZIP unchanged
- corrected full v4.1 script and output unchanged

## Run

```bash
python -B scripts/run_trace_net_executive_tiff_demo_v5_fast10_deep.py --heartbeat-seconds 5
```

Optional rehearsal without page embeddings:

```bash
python -B scripts/run_trace_net_executive_tiff_demo_v5_fast10_deep.py --heartbeat-seconds 5 --skip-embeddings
```
