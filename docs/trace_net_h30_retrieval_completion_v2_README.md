# TRACE-Net H30 Retrieval Completion v2

This patch completes the route execution and rendering gaps found in the OpenWebUI live regression.

## What it changes

- document/page navigation preserves matching visual, OCR, table, candidate, and semantic page leads
- local read-only JSON/JSONL resolver searches current indexed TRACE-Net artifacts
- OCR route reports actual stored OCR text, engine, confidence, and page when available
- aggregation reports unique pages, documents, evidence families, scan scope, and capping
- multi-question research renders a separate result bucket for every requested claim
- source-citation/source-trace-ready local rows can be promoted to direct evidence
- route-specific clue rendering suppresses irrelevant nomenclature echoes
- Gemma receives retrieval-completion structures only as bounded context
- six additional Engram memories capture the live regression lessons

## Safety

- no database writes
- no source-truth mutation
- no unmarked OCR, visual, graph, table, candidate, or semantic record is promoted
- local artifact scanning is bounded and cached
- exact mismatched part numbers are filtered
