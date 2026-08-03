# TRACE-Net TIFF Content Gemma Evidence Pack Router v4

This runner builds on router v3 and fixes remaining QA issues observed in the 50-question TIFF-content Gemma run.

## Changes

- Detects malformed partial answers, such as truncated part numbers (`120-`).
- Uses deterministic route answers directly for structured page/list/identifier questions where Gemma drifted in v3.
- Separates Figure visual page evidence from supporting OCR/IPL page evidence.
- Adds an exact part+nomenclature route for questions like `120-36833-001` nomenclature.
- Filters obvious non-part values such as ATA identifiers, raw page counters, and JSON escape junk from part-number summaries.
- Adds extraction-issue routing for low-confidence OCR/extraction questions.
- Adds source-trace-ready claim-category routing for citation/proof summary questions.

## Safety contract

Read-only. No source-truth mutation. No Postgres/Qdrant/OpenSearch writes. No answer permission. Route summaries are selected-evidence summaries only and do not prove eligibility, fit, approval, interchangeability, effectivity, or installation approval unless explicit source evidence supports that exact claim.
