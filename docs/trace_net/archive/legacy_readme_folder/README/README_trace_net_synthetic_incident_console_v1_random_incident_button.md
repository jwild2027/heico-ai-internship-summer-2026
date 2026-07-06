# TRACE-Net Synthetic Incident Console v1 Random Incident Button Fix

This small follow-up adds a one-click random synthetic incident workflow to the TRACE-Net Synthetic Incident Console.

## What changed

The console now includes:

```text
Create random incident
```

This button picks from safe synthetic issue templates across TRACE-Net origins such as OCR, table extraction, visual diagrams, graph integrity, retrieval, answer gate, feedback memory, trust authority, and human review.

The generated incident is marked:

```text
randomly_generated = true
synthetic_only = true
affects_real_pipeline = false
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
raw_feedback_direct_to_llm = false
```

## New API endpoints

```text
POST /api/incidents/random
GET  /api/simulate/random
```

Example:

```bash
curl -s -X POST http://127.0.0.1:8011/api/incidents/random \
  -H "Content-Type: application/json" \
  -d '{}' \
  | python -m json.tool
```

## Apply patch

```bash
unzip -o /c/Users/juswil/Downloads/tracenet_synthetic_incident_console_v1_random_button_patch.zip -d .
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_synthetic_incident_console_v1.py \
  tests/unit/test_trace_net_synthetic_incident_console_v1_quality.py \
  tests/unit/test_trace_net_synthetic_incident_console_v1_script_imports.py \
  -q
```

Expected:

```text
13 passed
```

## Start console

```bash
python scripts/run_trace_net_synthetic_incident_console_v1.py \
  --output-dir local_data/organization/trace_net/synthetic_incident_console \
  --host 127.0.0.1 \
  --port 8011 \
  --open
```

Open:

```text
http://127.0.0.1:8011/
```

Then click:

```text
Create random incident
```

