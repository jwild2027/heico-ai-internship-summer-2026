# TRACE-Net Guided Candidate Discovery v4

Adds a stricter guided candidate discovery runner for low-context part lookup.

## Purpose

This runner handles questions such as:

> I am looking for a part that starts with numbers 2 and 4 but I do not have the rest.

It returns candidate routes and clarifying questions. It does **not** grant final answer permission.

## v4 fixes

- Rejects UUID/hash-like hyphenated tokens such as `248c-5c38-8683`.
- Rejects `.tif` / filename/page artifact tokens such as `00000024.tif`.
- Rejects decimal OCR noise such as `24.689877`.
- Keeps real-looking aviation part numbers such as `244CS-3-2`, `MS24693-C5`, and `120-48024-001`.
- Cleans polluted nomenclature labels such as `HIGH_NAVIGATION_CONFIDENCE`, `HAS_TABLE_ROW`, and source-bound prompt labels.
- Keeps strict-prefix candidates separate from weaker related candidates.

## Safety contract

- Read-only local artifact scan.
- No source-truth mutation.
- No Postgres/Qdrant/OpenSearch writes.
- `final_answer_allowed=false` for all candidate-discovery results.

## Example

```bash
python -B scripts/run_trace_net_guided_candidate_discovery_v4.py \
  --artifact-root local_data/organization/trace_net \
  --output-dir /data/trace_net_runs/guided_candidate_discovery_v4 \
  --question "I am looking for a part that starts with numbers 2 and 4 but I do not have the rest" \
  --top-k 8 \
  --loose-top-k 8
```

Outputs:

- `summary.json`
- `candidate_discovery_results.jsonl`
- `candidate_discovery_view.txt`
