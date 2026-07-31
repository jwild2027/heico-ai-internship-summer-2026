# TRACE-Net Executive TIFF Demo v5 — Deep Fast10

This is a separate presentation mode for a short executive demonstration. It does not replace v2, v3, or the corrected full-corpus v4.1 mode.

## Default source window

The demo copies original TIFF pages 339 through 348 into a temporary ten-page ZIP. That window includes the evidence area around pages 342–344 used by the included part and next-higher-assembly example questions.

## Visible chronology

1. Print the ten original source pages selected.
2. Run OCR and print `OCR PROGRESS 01/10` through `10/10`.
3. Execute all nine build stages and their nine quality checks.
4. Print the OCR result for every page.
5. Resolve and print exactly one final page class per page.
6. Reject the presentation if any page is unknown.
7. Print `GRAPH NODES MADE` and `GRAPH EDGES MADE`.
8. Print the six Engram layers.
9. Run and print BGE-M3 embedding progress for each page.
10. Ask two example questions.
11. Print deterministic query atoms, route choice, bounded tunnels, retrieval evidence, evidence envelope, Engram update, one Gemma call, and final validators.
12. Print the final cited answer and safety summary.

## Classification contract

The final retry/probe field `final_validated_operational_route` is authoritative. The display gate requires:

- expected page count: 10
- final classified page count: 10
- unknown page count: 0
- duplicate page ID count: 0

Only these four final display classes are allowed:

- blank / nearly blank
- normal text / procedure
- table / illustrated parts list
- image / diagram

## Safety

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
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
