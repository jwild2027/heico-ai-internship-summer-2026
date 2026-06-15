# TRACE-Net Table Understanding v1

Step 15 turns existing table-candidate, table-tile, and refined table-text artifacts into structured table-understanding records.

This is a read-only TRACE-Net stage. It does not mutate Postgres, Qdrant, source TIFF/OCR files, trust, citations, or source truth.

## Purpose

TRACE-Net already has table-related front-end artifacts, including all-page table scans, table tile plans, and refined table tile text. This module adds a conservative table-understanding layer:

```text
page element registry
  -> table-relevant pages
  -> refined table tile text
  -> deterministic row/cell grabbing
  -> table type classification
  -> graph attachment plan
  -> safety and quality checks
```

## Cell grabbing algorithm

The cell grabber is deterministic and conservative:

```text
1. Clean OCR/table lines.
2. Prefer known token spans:
   - part numbers
   - ATA codes
   - dates
   - IPL/page references
   - index labels
3. Fall back to whitespace/grid splitting.
4. Attach row/cell confidence and token type metadata.
5. Keep table records gated; no table record can answer directly.
```

Algorithm name:

```text
trace_net_token_span_plus_whitespace_grid_v1
```

This is not a final image-table OCR model. It structures the existing refined table text and prepares table evidence for later trust/citation/graph stages.

## Safety contract

Table records are not final answers.

Every record uses:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
final_answer_allowed = false
llm_freeform_answer_allowed = false
```

## Outputs

Default output directory:

```text
local_data/organization/trace_net/table_understanding/
```

Files written:

```text
trace_net_table_understanding_v1.json
trace_net_table_understanding_v1_records.jsonl
trace_net_table_understanding_v1_rows.jsonl
trace_net_table_understanding_v1_cells.jsonl
trace_net_table_understanding_v1_graph_attachment_plan.jsonl
trace_net_table_understanding_v1_summary.json
trace_net_table_understanding_v1_manifest.json
trace_net_table_understanding_v1_quality.json
trace_net_table_understanding_v1.md
trace_net_table_understanding_v1.html
```

## Build

```bash
python scripts/build_trace_net_table_understanding_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --table-tile-text-refined-records local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_records.jsonl \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --table-candidate-summary local_data/organization/table_extraction/all_page_scan/table_candidate_summary.json \
  --table-tile-summary local_data/organization/table_extraction/table_tile_summary.json \
  --table-tile-text-refined-summary local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_summary.json \
  --table-tile-text-refined-quality local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_quality.json \
  --output-dir local_data/organization/trace_net/table_understanding \
  --min-table-records 20 \
  --min-pages-with-structured-cells 20 \
  --min-cell-records 100 \
  --min-table-types-assigned 20 \
  --min-source-trace-tables 20 \
  --quality
```

The suggested thresholds match the current refined-table-text checkpoint, which has 120 refined tile-text records across 20 pages.

## Quality check

```bash
python scripts/check_trace_net_table_understanding_v1_quality.py \
  --report-path local_data/organization/trace_net/table_understanding/trace_net_table_understanding_v1.json \
  --min-table-records 20 \
  --min-pages-with-structured-cells 20 \
  --min-cell-records 100 \
  --min-table-types-assigned 20 \
  --min-source-trace-tables 20 \
  --write-json
```

## Inspect cells

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path('local_data/organization/trace_net/table_understanding/trace_net_table_understanding_v1.json')
payload = json.loads(path.read_text(encoding='utf-8'))
print('quality_status:', payload['quality_status'])
print('summary:', payload['summary'])

for record in payload['records'][:3]:
    print('\npage_id:', record['page_id'])
    print('table_type:', record['table_type'])
    print('trust_tier:', record['trust_tier'])
    print('rows:', record['row_count'], 'cells:', record['cell_count'])
    print('cell_grabber_confidence:', record['cell_grabber_confidence'])
    for row in record['rows'][:3]:
        row_cells = [c for c in record['cells'] if c['row_id'] == row['row_id']]
        print('  row:', [c['text'] for c in row_cells])
PY
```

## Commit patch files only

```bash
git add \
  tiff/trace_net_table_understanding_v1.py \
  scripts/build_trace_net_table_understanding_v1.py \
  scripts/check_trace_net_table_understanding_v1_quality.py \
  tests/unit/test_trace_net_table_understanding_v1.py \
  tests/unit/test_trace_net_table_understanding_v1_quality.py \
  tests/unit/test_trace_net_table_understanding_v1_script_imports.py \
  README_trace_net_table_understanding_v1.md

git commit -m "Add TRACE-Net table understanding v1"
```

Do not commit generated `local_data/...` artifacts unless you intentionally want the local branch to include them.
