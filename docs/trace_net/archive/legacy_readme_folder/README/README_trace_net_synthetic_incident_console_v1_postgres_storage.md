# TRACE-Net Synthetic Incident Console v1 - Postgres Storage

This patch moves the synthetic incident console from local-only JSONL storage to dual storage:

- `--storage-mode local` keeps the current local JSONL behavior.
- `--storage-mode postgres` stores incidents in Postgres table `trace_net_synthetic_incident_events`.

Local JSON/JSONL/HTML reports are still written as snapshots for audit/debug. Postgres becomes the server source of truth for incident events.

## Safety contract

Synthetic incident records remain operational/admin records only:

- no Qdrant writes
- no OpenSearch writes
- no source file writes
- no graph truth writes
- no answer authority
- no claim proof authority
- no source truth mutation
- raw feedback is not sent directly to the LLM

## Initialize Postgres storage

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"

python scripts/init_trace_net_synthetic_incident_console_postgres_v1.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --postgres-table trace_net_synthetic_incident_events
```

Alternative through the console runner:

```bash
python scripts/run_trace_net_synthetic_incident_console_v1.py \
  --storage-mode postgres \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --init-postgres \
  --build-only
```

## Start Postgres-backed console

```bash
python scripts/run_trace_net_synthetic_incident_console_v1.py \
  --storage-mode postgres \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --host 127.0.0.1 \
  --port 8011 \
  --open
```

## Create a random incident through API

```bash
curl -s -X POST http://127.0.0.1:8011/api/incidents/random \
  -H "Content-Type: application/json" \
  -d '{}' \
  | python -m json.tool
```

## Verify incidents in Postgres

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select severity, origin_category, count(*) from trace_net_synthetic_incident_events group by severity, origin_category order by severity, origin_category;"
```

## Clear Postgres incidents

```bash
python scripts/run_trace_net_synthetic_incident_console_v1.py \
  --storage-mode postgres \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --clear \
  --build-only
```

## Local fallback

```bash
python scripts/run_trace_net_synthetic_incident_console_v1.py \
  --storage-mode local \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --host 127.0.0.1 \
  --port 8011 \
  --open
```
