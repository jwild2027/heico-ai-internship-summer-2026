# TRACE-Net Synthetic Incident Console v1

This module adds a small local IT/admin UI for testing synthetic TRACE-Net incidents and organized alert messages.

It is intentionally synthetic-only. It does not write to Postgres, Qdrant, OpenSearch, Chroma, Open WebUI, source files, graph truth, trust records, or answer artifacts.

Default local port:

```text
127.0.0.1:8011
```

This avoids the current local Docker ports:

```text
Postgres: 5432
Qdrant: 6333 / 6334
Open WebUI: 3000
Chroma: 8000
```

## Files

```text
tiff/trace_net_synthetic_incident_console_v1.py
scripts/run_trace_net_synthetic_incident_console_v1.py
scripts/check_trace_net_synthetic_incident_console_v1_quality.py
tests/unit/test_trace_net_synthetic_incident_console_v1.py
tests/unit/test_trace_net_synthetic_incident_console_v1_quality.py
tests/unit/test_trace_net_synthetic_incident_console_v1_script_imports.py
```

## Apply patch

```bash
unzip -o /c/Users/juswil/Downloads/tracenet_synthetic_incident_console_v1_patch.zip -d .
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_synthetic_incident_console_v1.py \
  tests/unit/test_trace_net_synthetic_incident_console_v1_quality.py \
  tests/unit/test_trace_net_synthetic_incident_console_v1_script_imports.py \
  -q
```

## Build static artifacts only

```bash
python scripts/run_trace_net_synthetic_incident_console_v1.py \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --seed-samples \
  --build-only
```

## Run the local UI

```bash
python scripts/run_trace_net_synthetic_incident_console_v1.py \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --host 127.0.0.1 \
  --port 8011 \
  --open
```

Then open:

```text
http://127.0.0.1:8011/
```

## What the UI can do

Buttons create synthetic incidents for these origins:

```text
source_ingest
ocr_text
page_registry
table_extraction
visual_diagram
graph_integrity
semantic_vector
keyword_search
retrieval
answer_gate
feedback_memory
incremental_ops
llm_advisory
security_leakage
trust_authority
community_graph
human_review
```

The UI shows organized alert cards by severity:

```text
critical
warning
review
info
```

## API endpoints

```text
GET  /api/health
GET  /api/incidents
POST /api/incidents
POST /api/incidents/clear
GET  /api/simulate/<origin_category>
```

Example API call:

```bash
curl -s -X POST http://127.0.0.1:8011/api/incidents \
  -H "Content-Type: application/json" \
  -d '{"origin_category":"visual_diagram","severity":"review","message":"Synthetic callout verification needed."}' \
  | python -m json.tool
```

## Quality check

```bash
python scripts/check_trace_net_synthetic_incident_console_v1_quality.py \
  --report-path local_data/organization/trace_net/synthetic_incident_console/trace_net_synthetic_incident_console_v1.json \
  --min-incidents 1 \
  --write-json
```

## Safety contract

Every synthetic incident is marked:

```text
synthetic_only = true
affects_real_pipeline = false
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
raw_feedback_direct_to_llm = false
```

The console is for IT/admin workflow testing only. It is not a production incident executor.

## Random synthetic incidents

A follow-up patch adds a **Create random incident** button and these endpoints:

```text
POST /api/incidents/random
GET  /api/simulate/random
```

Random incidents are still synthetic-only and safe. They are marked `randomly_generated = true` and cannot answer, prove claims, mutate source truth, or affect the real pipeline.
