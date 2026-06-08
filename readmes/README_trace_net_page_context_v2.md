# TRACE-Net Page Context v2 / Query Guidance Overlay

This module upgrades page context from a short topic summary into a structured RAG guidance card.

It adds:

- retrieval summary
- answerable questions
- retrieval cues and aliases
- important entities
- component families
- important parts
- nearby context
- source grounding phrases
- not-good-for guardrails
- fixed authority metadata

Safety rules:

- page context v2 is derived retrieval context only
- page context v2 is not canonical source truth
- page context v2 cannot answer directly
- page context v2 requires source citation
- page context v2 does not mutate source truth

## Pilot with Gemma 3 12B through Ollama

```bash
python scripts/generate_trace_net_page_context_v2.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --model gemma3:12B \
  --limit 10 \
  --force \
  --progress \
  --open
```

## Full 509-page run

```bash
python scripts/generate_trace_net_page_context_v2.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --model gemma3:12B \
  --limit 509 \
  --force \
  --progress \
  --open
```

## Missing-only rerun

```bash
python scripts/generate_trace_net_page_context_v2.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --model gemma3:12B \
  --limit 509 \
  --missing-only \
  --progress \
  --open
```

## Fast heuristic fallback

```bash
python scripts/generate_trace_net_page_context_v2.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --provider heuristic \
  --limit 509 \
  --force \
  --progress \
  --open
```

## Quality gate

```bash
python scripts/check_trace_net_page_context_v2_quality.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --write-json \
  --min-context-v2-records 509 \
  --min-pages-with-context-v2 509 \
  --min-records-with-retrieval-cues 495 \
  --min-records-with-answerable-questions 495 \
  --min-context-v2-graph-nodes 509 \
  --min-has-context-v2-edges 509 \
  --max-direct-answer-context-records 0 \
  --max-canonical-source-truth-context-records 0 \
  --max-source-truth-mutations 0
```

## Useful SQL checks

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select role, subrole, count(*) from page_context_v2_records group by role, subrole order by count(*) desc limit 20;"
```

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select page_id, role, subrole, retrieval_cues from page_context_v2_records where page_id='t_p_120_1176_p000015';"
```

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select count(*) from page_context_v2_records where coalesce((authority->>'can_answer_directly')::boolean,false)=true or coalesce((authority->>'canonical_source_truth')::boolean,false)=true;"
```

Expected unsafe authority count: `0`.
