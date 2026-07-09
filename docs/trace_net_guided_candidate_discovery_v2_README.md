# TRACE-Net Guided Candidate Discovery v2

Adds a stricter low-context candidate discovery runner for partial part-number questions.

## What changed from v1

- Separates strict prefix matches from weaker contains/overlap matches.
- If the user says a part starts with `24`, only candidates whose normalized part number starts with `24` are primary matches.
- Related candidates that merely contain `24` are labeled as weaker and are not treated as exact matches.
- Adds conservative part-token filtering to avoid treating ATA codes, junk escape strings, years, and short counters as part numbers.
- Avoids converting part-like strings such as `120TP250001` into fake page IDs like `p250001`.
- Keeps final answer permission disabled: candidate routes are discovery hints only.

## Example

```bash
PYTHONUNBUFFERED=1 python3 -u scripts/run_trace_net_guided_candidate_discovery_v2.py \
  --artifact-root local_data/organization/trace_net \
  --output-dir /data/trace_net_runs/guided_candidate_discovery_v2 \
  --question "I am looking for a part that starts with numbers 2 and 4 but I do not have the rest" \
  --top-k 8 \
  --loose-top-k 8
```

Outputs:

- `summary.json`
- `candidate_discovery_results.jsonl`
- `candidate_discovery_view.txt`

## Safety contract

- Read-only artifact scan.
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- `final_answer_allowed=false` for all candidate discovery results.
