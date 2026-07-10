# TRACE-Net Router Proxy v6 + Gated Visual Route v1.1

This patch fixes the v1 router trigger behavior.

## What was wrong

The word `part` was too broad as a visual trigger. A query like:

```text
I only know the part starts with 24
```

was incorrectly routed to `gated_image_visual`.

## Fix

v1.1 makes visual triggering stricter:

- `diagram`, `figure`, `callout`, `visual`, `drawing`, `exploded view`, etc. still trigger visual route.
- generic `part`, `parts`, `item`, `seat`, and `assembly` do **not** trigger visual route by themselves.
- partial lookup phrases such as `only know`, `starts with`, `begins with`, and `contains` bypass visual route and go to the existing v6 fallback/guided discovery unless visual mode is explicitly forced.

## Route order

```text
visual/diagram/figure/callout query
→ gated_image_visual route

partial part lookup
→ existing v6 guided/normal router fallback

nonvisual query
→ existing v6 router fallback
```

## Safety

- visual route remains read-only
- no visual-route Ollama call
- no visual-route LLM call
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch write
- `final_answer_allowed=false`
- `answer_permission=false`
