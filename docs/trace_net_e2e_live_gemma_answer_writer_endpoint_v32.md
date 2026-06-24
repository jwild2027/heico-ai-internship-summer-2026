# TRACE-Net E2E Live Gemma Answer Writer Endpoint v32.1 Hotfix

This hotfix keeps the v32 always-on Gemma design, but makes the prompt compact and adds answer-budget/timeout fallback telemetry.

## Contract
- TRACE-Net still builds the package before Gemma sees the query.
- Gemma is still called for every answer in this endpoint mode.
- Compact prompt mode sends task-specific facts instead of a large JSON package.
- `max_tokens` limits Gemma's answer budget for simple answers.
- If Gemma errors or times out, TRACE-Net returns the deterministic final-gated fallback answer.
- Final gate remains mandatory.

## New runtime options
- `--llm-prompt-mode compact` default; use `full` only for debugging.
- `--llm-max-output-tokens 180` default short answer budget.
- `--request-timeout <seconds>` can be set lower during laptop demos so WebUI does not hang.

## New telemetry
- `llm_prompt_mode`
- `prompt_char_count`
- `prompt_token_estimate`
- `llm_max_output_tokens`
- `llm_timeout_budget_ms`
- `llm_timed_out`
- `fallback_answer_used`

## Purpose
This is step 1 only: make always-on Gemma usable with compact packages. It does not add the next batch of missing deterministic/page/list intents.

## v32.2 normal intent package hotfix

This hotfix keeps always-on Gemma and compact prompt mode, then adds/locks package support for normal WebUI questions that should not fall to audit-only:

- corpus page count (`how many pages are there`)
- covered part number listing (`List covered part numbers`)
- covered part number drill-down by field
- page-scoped source-truth records
- page-scoped covered part numbers
- page profile package using page records plus v2 summary guidance

All supported normal intents still flow through: TRACE-Net package -> Gemma answer writer -> final gate -> WebUI answer.
