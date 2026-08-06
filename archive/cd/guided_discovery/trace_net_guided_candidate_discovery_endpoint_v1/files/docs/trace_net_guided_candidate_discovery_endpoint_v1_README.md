# TRACE-Net guided candidate discovery endpoint v1

This patch exposes `run_trace_net_guided_candidate_discovery_v4.py` through a small local HTTP API.

## Routes

- `GET /health`
- `GET /api/trace-net/guided-discovery/health`
- `POST /api/trace-net/guided-discovery`

## Safety contract

The endpoint is read-only. It scans local TRACE-Net artifacts and returns candidate routes. It does not write to Postgres, Qdrant, or OpenSearch. It does not mutate source truth. It always keeps `final_answer_allowed=false` because guided discovery is a candidate-finding workflow, not a final proof workflow.

## Example server command

```bash
python3 -B scripts/serve_trace_net_guided_candidate_discovery_endpoint_v1.py \
  --host 127.0.0.1 \
  --port 8016 \
  --artifact-root local_data/organization/trace_net \
  --output-dir /data/trace_net_runs/guided_candidate_discovery_endpoint_v1 \
  --top-k 8 \
  --loose-top-k 8
```

## Example request

```bash
curl -s http://127.0.0.1:8016/api/trace-net/guided-discovery \
  -H "Content-Type: application/json" \
  -d '{"question":"I am looking for a part that starts with numbers 2 and 4 but I do not have the rest","top_k":8,"loose_top_k":8}'
```

## Response shape

The response includes:

- `intent`
- `known_clues`
- `missing_clues`
- `clarifying_questions`
- `strict_prefix_candidates`
- `loose_candidates`
- `candidate_routes`
- `source_trace_status: candidate-discovery-only`
- `final_answer_allowed: false`
- safety counts set to zero

## Notes

This endpoint intentionally uses a different response shape than normal answer Q&A. Normal Q&A returns an answer draft plus citations. Guided discovery returns clarifying questions and route cards.
