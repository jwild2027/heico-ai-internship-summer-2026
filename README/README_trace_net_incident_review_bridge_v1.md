# TRACE-Net Incident -> Review Task Bridge v1

This module converts TRACE-Net operational incidents into human-review tasks.

It bridges:

```text
Incident Console / Postgres incident table
-> review task records
-> future human review queue / triage / decisions
```

## Safety contract

Incidents are operational signals only:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
raw_feedback_direct_to_llm = false
```

An incident can create review work. It cannot become source truth, evidence proof, or answer authority.

## Inputs

Use one or more of:

```text
--database-url postgresql://...
--incidents-jsonl path/to/incidents.jsonl
--incident-report path/to/report.json
```

For Postgres mode, the default table is:

```text
trace_net_synthetic_incident_events
```

## Output

```text
local_data/organization/trace_net/incident_review_bridge/
```

Generated files:

```text
trace_net_incident_review_bridge_v1.json
trace_net_incident_review_bridge_v1_tasks.jsonl
trace_net_incident_review_bridge_v1_incidents.jsonl
trace_net_incident_review_bridge_v1_summary.json
trace_net_incident_review_bridge_v1_quality.json
trace_net_incident_review_bridge_v1_manifest.json
trace_net_incident_review_bridge_v1.md
trace_net_incident_review_bridge_v1.html
```

## Run with Postgres incidents

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"

python scripts/build_trace_net_incident_review_bridge_v1.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --postgres-table trace_net_synthetic_incident_events \
  --output-dir local_data/organization/trace_net/incident_review_bridge \
  --min-incidents 1 \
  --min-review-tasks 1 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_incident_review_bridge_v1_quality.py \
  --report-path local_data/organization/trace_net/incident_review_bridge/trace_net_incident_review_bridge_v1.json \
  --min-incidents 1 \
  --min-review-tasks 1 \
  --write-json
```

## Inspect tasks

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("local_data/organization/trace_net/incident_review_bridge/trace_net_incident_review_bridge_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("summary:", payload["summary"])

for task in payload["review_tasks"][:20]:
    print()
    print("task:", task["review_task_id"])
    print("priority:", task["priority"])
    print("type:", task["task_type"])
    print("incident:", task["origin_incident_id"])
    print("target:", task["target_type"], task["target_id"])
    print("pages:", task["page_ids"][:5])
    print("reason:", task["reason"])
    print("action:", task["recommended_action"])
PY
```
