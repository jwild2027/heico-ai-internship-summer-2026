# TRACE-Net Synthetic Incident Postgres Smoke v1

This patch adds a repeatable smoke verification for the Postgres-backed synthetic incident console.

It verifies:

- Postgres schema can initialize.
- A safe random synthetic incident can be inserted.
- The inserted incident can be read back from Postgres.
- The console can build a Postgres-backed snapshot report.
- Synthetic incidents remain non-answering, non-proof, and non-mutating.

## Apply

```bash
unzip -o /c/Users/juswil/Downloads/tracenet_synthetic_incident_postgres_smoke_v1_patch.zip -d .
```

## Test

```bash
python -m pytest \
  tests/unit/test_trace_net_synthetic_incident_postgres_smoke_v1.py \
  tests/unit/test_trace_net_synthetic_incident_postgres_smoke_v1_quality.py \
  tests/unit/test_trace_net_synthetic_incident_postgres_smoke_v1_script_imports.py \
  -q
```

## Run smoke

```bash
docker start trace-net-postgres
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"

python scripts/smoke_trace_net_synthetic_incident_postgres_v1.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --output-dir local_data/organization/trace_net/synthetic_incident_console_postgres_smoke \
  --postgres-table trace_net_synthetic_incident_events \
  --random-incident-count 1 \
  --min-inserted-incidents 1 \
  --quality
```

## Check quality

```bash
python scripts/check_trace_net_synthetic_incident_postgres_smoke_v1_quality.py \
  --report-path local_data/organization/trace_net/synthetic_incident_console_postgres_smoke/trace_net_synthetic_incident_postgres_smoke_v1.json \
  --min-inserted-incidents 1 \
  --write-json
```

## Verify table

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select incident_id, severity, origin_category, target_type, target_id, synthetic_only from trace_net_synthetic_incident_events order by created_at desc limit 10;"
```

## Safety

The smoke creates synthetic admin/test records only. It does not write graph truth, Qdrant, OpenSearch, trust records, citations, or final answer artifacts.
