# TIFF Document Graph Traceability Args Fix

Adds missing trace CLI support for:

- `--ata <ATA_CODE>`
- `--max-pages <N>` as an alias for trace sample limit
- `--vector-chunk <CHUNK_ID>`
- `--vector-score <SCORE>`

This keeps the traceability command aligned with the intended graph traversal tests:

```text
part -> pages -> source links/context
page -> document/ATA/parts/source/context
ATA -> pages -> source links/context/parts
Qdrant payload -> page -> graph/source/context
```

Run:

```bash
python -m pytest tests/unit/test_tiff_document_graph_traceability.py -q
python scripts/trace_document_graph.py --ata 25-21-00 --max-pages 8 --strict --write-json
python scripts/trace_document_graph.py --vector-page t_p_120_1176_p000495 --vector-chunk chunk_t_p_120_1176_p000495_001 --vector-score 0.635 --strict --write-json
```
