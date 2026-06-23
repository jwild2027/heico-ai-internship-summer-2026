# TRACE-Net OpenSearch Live Loader v1

This module turns the PASS OpenSearch Adapter and Loader Smoke artifacts into a real local OpenSearch index named `trace_net_safe_search_v1`.

The loader is intentionally conservative:

- it only indexes documents that already have page/source lineage;
- it drops unsafe, untraceable, raw feedback, raw visual, or raw unfiltered OCR records;
- it only writes to OpenSearch when `--allow-opensearch-writes` is explicitly supplied;
- it never writes to Postgres, Qdrant, source truth, graph state, or final-answer authority;
- indexed records remain retrieval-only and cannot answer directly or prove claims.

## Inputs

- `local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json`
- `local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json`

## Outputs

- `local_data/organization/trace_net/opensearch_live_loader/trace_net_opensearch_live_loader_v1.json`
- `trace_net_opensearch_live_loader_v1_quality.json`
- `trace_net_opensearch_live_loader_v1_summary.json`
- `trace_net_opensearch_live_loader_v1_manifest.json`
- `trace_net_opensearch_live_loader_v1.md`

## Local OpenSearch container

Suggested local development container:

```bash
docker run -d --name trace-net-opensearch \
  -p 9200:9200 \
  -p 9600:9600 \
  -e "discovery.type=single-node" \
  -e "DISABLE_INSTALL_DEMO_CONFIG=true" \
  -e "DISABLE_SECURITY_PLUGIN=true" \
  -e "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m" \
  --ulimit nofile=65536:65536 \
  opensearchproject/opensearch:latest
```

Then check:

```bash
for i in {1..90}; do
  echo "waiting for OpenSearch... attempt $i"
  if curl -s http://localhost:9200/_cluster/health | python -m json.tool; then
    echo "OpenSearch is ready"
    break
  fi
  sleep 5
done
```

## Live smoke query notes

The safe adapter schema commonly stores searchable content in `text` and `title`,
not only in legacy `search_text`. Live smoke queries therefore search `text`,
`title`, `part_number`, `part_numbers`, page lineage fields, and legacy
`search_text` so that a correctly loaded index is not marked unhealthy by a
field-name mismatch.

## Live load command

```bash
python scripts/build_trace_net_opensearch_live_loader_v1.py \
  --opensearch-adapter local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --loader-smoke local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json \
  --output-dir local_data/organization/trace_net/opensearch_live_loader \
  --opensearch-url http://localhost:9200 \
  --index-name trace_net_safe_search_v1 \
  --recreate-index \
  --bulk-load \
  --refresh \
  --run-smoke-queries \
  --allow-opensearch-writes \
  --min-documents 100 \
  --min-page-scoped-documents 100 \
  --min-loaded-documents 100 \
  --min-smoke-queries 3 \
  --require-adapter-quality-pass \
  --require-loader-smoke-quality-pass \
  --require-mapping \
  --require-bulk-load \
  --require-live-read-check \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_opensearch_live_loader_v1_quality.py \
  --report-path local_data/organization/trace_net/opensearch_live_loader/trace_net_opensearch_live_loader_v1.json \
  --min-documents 100 \
  --min-page-scoped-documents 100 \
  --min-loaded-documents 100 \
  --min-smoke-queries 3 \
  --require-adapter-quality-pass \
  --require-loader-smoke-quality-pass \
  --require-mapping \
  --require-bulk-load \
  --require-live-read-check \
  --allow-opensearch-writes \
  --write-json
```

## v1 Smoke Validation Note

Live OpenSearch smoke queries must target the fields that actually exist in the safe-document mapping.
The searchable body is stored primarily in `text` and `title`; `search_text` is treated only as a legacy fallback.
Table-cell exact smoke checks intentionally avoid hard-filtering by `document_type` so a loaded exact value can be validated through table-cell, table-row, or part-candidate documents while still preserving retrieval-only authority.
