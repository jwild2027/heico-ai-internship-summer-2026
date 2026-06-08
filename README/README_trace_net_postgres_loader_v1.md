# TRACE-Net PostgreSQL Loader v1

Imports local OCR / TRACE-Net artifacts into a local PostgreSQL database for testing before the production server stack is ready.

Large binaries stay on disk. PostgreSQL stores paths, OCR text, graph records, evidence records, RAG candidates, citations, feedback, and quality summaries.

## Install dependency

```bash
pip install "psycopg[binary]"
```

or:

```bash
pip install psycopg2-binary
```

## Start local PostgreSQL with Docker

```bash
docker run --name trace-net-postgres \
  -e POSTGRES_USER=tracenet \
  -e POSTGRES_PASSWORD=tracenet \
  -e POSTGRES_DB=tracenet_dev \
  -p 5432:5432 \
  -d postgres:16
```

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"
```

## Initialize schema

```bash
python scripts/init_trace_net_postgres.py \
  --database-url "$TRACE_NET_DATABASE_URL"
```

## Load local artifacts

```bash
python scripts/load_trace_net_postgres.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --ocr-export-dir local_data/ocr/full_509_psm3 \
  --ocr-depth-audit local_data/ocr/full_509_psm3_depth_audit.json \
  --organization-dir local_data/organization \
  --trace-net-dir local_data/organization/trace_net \
  --source-zip "$METADATA_ZIP" \
  --upsert
```

## Quality gate

```bash
python scripts/check_trace_net_postgres_quality.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --write-json \
  --min-pages 509 \
  --min-ocr-records 509 \
  --min-rag-candidates 1426 \
  --min-citations 1426 \
  --max-unsafe-rag-candidates 0 \
  --max-missing-citation-source-url 0
```

## Dry run without PostgreSQL

```bash
python scripts/load_trace_net_postgres.py \
  --ocr-export-dir local_data/ocr/full_509_psm3 \
  --ocr-depth-audit local_data/ocr/full_509_psm3_depth_audit.json \
  --organization-dir local_data/organization \
  --trace-net-dir local_data/organization/trace_net \
  --source-zip "$METADATA_ZIP" \
  --dry-run
```

## Tables created

- `source_packages`
- `documents`
- `pages`
- `ocr_records`
- `graph_nodes`
- `graph_edges`
- `evidence_consensus_records`
- `stage5_decision_records`
- `rag_eligibility_records`
- `rag_candidate_chunks`
- `source_citations`
- `ask_runs`
- `feedback_events`
- `feedback_policy_signals`
- `quality_runs`
- `trace_net_load_runs`

## Quick SQL checks

```bash
psql "$TRACE_NET_DATABASE_URL" -c "select count(*) from pages;"
psql "$TRACE_NET_DATABASE_URL" -c "select classification, count(*) from ocr_records group by classification order by count(*) desc;"
psql "$TRACE_NET_DATABASE_URL" -c "select rag_bucket, count(*) from rag_candidate_chunks group by rag_bucket order by rag_bucket;"
psql "$TRACE_NET_DATABASE_URL" -c "select page_id, rag_bucket, trust_tier, usable_confidence from rag_candidate_chunks where text ilike '%120-50645-009%' limit 20;"
```
