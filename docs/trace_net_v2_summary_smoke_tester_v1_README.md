# TRACE-Net V2 summary smoke tester v1

This patch adds a safe tester for the existing V2 summary guide.

It does not create a new V2 summary system. It imports and uses the existing implementation:

- `tiff/trace_net_page_context_v2.py`
- `heuristic_context_v2()`
- `build_prompt()`
- `sanitize_context_v2()`

## What it tests

The tester checks that V2 summaries/cards have the current query-guidance schema:

- page_id
- role
- subrole
- confidence
- short_summary
- retrieval_summary
- answerable_questions
- retrieval_cues
- important_entities
- component_families
- source_grounding
- not_good_for
- authority
- prompt_version

It also checks that V2 summaries remain guidance only:

- no answer permission
- no canonical source-truth claim
- no source-truth mutation
- no database/search/vector writes

## Why this exists

Before changing or rerunning V2 summaries at full scale, this gives a laptop-safe smoke test.
It can test a few pages from `local_data/organization/context/page_contexts.json` without calling Ollama or Postgres.

It can also audit an existing `trace_net_page_context_v2_records.jsonl` file if one already exists.
