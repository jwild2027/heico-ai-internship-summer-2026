# TRACE-Net Human Review Queue Triage / Dedup v1

This module converts the raw `trace_net_human_review_queue_v1` task list into reviewer-friendly triage cards.

The raw queue is intentionally complete and can contain many overlapping tasks per page. The triage layer groups those tasks into cards by page, community, or critical target so a reviewer sees one actionable card instead of many duplicated signals.

## Safety contract

The triage layer is advisory only.

It cannot:

- answer directly
- prove claims
- mutate source truth
- override citations
- override trust authority
- pass raw feedback directly to an LLM

## Inputs

```text
local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json
```

## Outputs

```text
local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json
local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1_cards.jsonl
local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1_summary.json
local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1_quality.json
local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.md
local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.html
```

## Run

```bash
python scripts/build_trace_net_human_review_triage_v1.py \
  --human-review-queue local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json \
  --output-dir local_data/organization/trace_net/human_review_triage \
  --min-triage-cards 1 \
  --min-high-priority-cards 1 \
  --require-source-queue-quality-pass \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_human_review_triage_v1_quality.py \
  --report-path local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json \
  --min-triage-cards 1 \
  --min-high-priority-cards 1 \
  --require-source-queue-quality-pass \
  --write-json
```

## Inspect cards

```bash
python - <<'PY'
import json
from pathlib import Path
from collections import Counter

path = Path("local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("summary:", payload["summary"])

cards = payload["triage_cards"]
print("priority_counts:", Counter(c["priority"] for c in cards))
print("card_type_counts:", Counter(c["card_type"] for c in cards))

for card in cards[:20]:
    print()
    print("card_id:", card["triage_card_id"])
    print("priority:", card["priority"])
    print("card_type:", card["card_type"])
    print("group:", card["group_kind"], card["group_value"])
    print("task_count:", card["task_count"])
    print("page_ids:", card["page_ids"][:10])
    print("reason:", card["reason_summary"][:500])
    print("action:", card["recommended_action"][:500])
    print("can_answer_directly:", card["can_answer_directly"])
    print("can_prove_claims:", card["can_prove_claims"])
    print("can_mutate_source_truth:", card["can_mutate_source_truth"])
PY
```

## Meaning

The raw queue answers:

```text
What individual review tasks exist?
```

The triage queue answers:

```text
What should a reviewer actually work on first?
```

Example:

```text
Page 000003 may have several raw tasks:
- review repaired table cells
- verify visual/callout candidates
- compare visual parts to catalog
- fishnet review required

The triage layer groups them into one high-priority page card.
```
