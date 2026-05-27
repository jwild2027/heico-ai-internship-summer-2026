# TIFF Part Catalog Filtering + QA Triage Patch

This patch tightens the part-number and nomenclature filters so OCR artifacts do not pollute the part catalog and QA reports.

## What changed

- Rejects ATA/page references such as `25-21-00-46` from `part_mentions`.
- Rejects manual/page labels such as `25-IPL`, `T.P`, `IGURE`, `SHEET`, and `PER STOCK` as catalog nomenclature.
- Filters QA reports so they focus on real-looking parts instead of OCR/page noise.
- Adds `scripts/inspect_part_number.py` for one-part triage.

## Rebuild required

Because this changes extraction rules, rebuild the database artifacts after installing:

```bash
python scripts/build_tiff_search_index.py --rescarta-export-dir local_data/rescarta_exports --output-db local_data/db/tiff_search.db
python scripts/rebuild_clean_part_catalog.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_chunks.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_embeddings.py --db-path local_data/db/tiff_search.db --model bge-m3:latest --reset
```

Then rerun QA:

```bash
python scripts/report_part_catalog_qa.py --config local_config.yaml
python scripts/evaluate_rag_questions.py --config local_config.yaml --questions local_data/evals/rag_eval_questions.json
```

Inspect one part:

```bash
python scripts/inspect_part_number.py --config local_config.yaml 120-37313-001
```
