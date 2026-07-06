# TRACE-Net H36 Complex Task Validator v1

H36 validates H35 custom task outputs with task-specific contracts.

It fixes a major grading issue from H35: negated forbidden claims such as
"does not verify interchangeability" are safe boundary statements, not unsafe claims.

## Checks

- negation-aware forbidden claim detection
- grouped citation syntax
- fallback usage
- answer length
- unique evidence label counts
- unique route counts
- quiz answer key presence
- quiz question count
- quiz limits/boundary question
- internal metadata quiz items such as `source_extractor_quality_pass`

## Safety

Artifact-only. No LLM calls. No live DB/vector/search IO. No source-truth mutation. No answer permission.
