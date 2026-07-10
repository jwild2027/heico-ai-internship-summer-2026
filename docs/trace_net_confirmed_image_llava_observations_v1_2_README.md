# TRACE-Net Confirmed Image LLaVA Observations v1.2

v1.2 tightens v1.1 after the second 5-page sample.

## Why

v1.1 was mechanically good, but sample inspection still showed:

- prompt leakage into `page_header_or_boilerplate_text`
- generic sentences kept as cleaned callouts
- generic subject guesses such as `aircraft structure`

## Fix

v1.2 adds:

- stronger prompt: JSON only, no prompt copying, callouts must be short strings
- generic subject normalization to `unknown`
- figure text cleanup when it says “not visible” / “not clear”
- deterministic filtering of prompt leaks
- deterministic filtering of generic callout sentences

## Safety

Still visual guidance only. OCR/table/source evidence remains authority for exact
text and exact part facts.
