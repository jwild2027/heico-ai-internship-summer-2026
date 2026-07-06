# TRACE-Net Page Context Pack v3.2

Page Context Pack v3.2 builds a source-bounded page binder for page-specific and complex TRACE-Net questions.

## Purpose

The model should still reason for complex questions, but it should reason from a controlled binder:

- proof/source locators first: source files, source links, OCR/source text, table evidence, exact part records
- guidance records second: graph neighbors, vector hits, visual summaries, route-only candidates
- explicit reasoning work order: allowed synthesis plus blocked overclaims

## v3.2 hydrator improvements

v3.2 improves the v3.1 page resolver with route-aware hydration:

- Adds source file/source link locators from route, OCR, graph, table, exact, and visual records.
- Follows linked JSONL sidecars such as `records_jsonl_path` so visual/OpenWebUI route manifests can attach real page cards.
- Extracts OCR text from common OCR keys and nested cells/rows/tiles.
- Adds visual guidance for image/visual pages while keeping it guidance-only.
- Moves unproven table/exact records into `route_guidance` instead of counting them as proof.
- Adds `route_evidence_priority` and per-page `page_reasoning_tasks` so Gemma can think through complex questions without overclaiming.

## Safety contract

- Read-only inputs.
- No Postgres, Qdrant, or OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- Guidance records cannot prove factual source claims unless backed by proof records.

## v3.3 exact page-number resolver

Numeric page labels are kept label-qualified (`label:48`) so a user request such as `--pages 48` resolves to source page 48 rather than a later source page whose manual label is 48. This prevents page 48 from being accidentally resolved to page 448.
