# TRACE-Net E2E Relationship Router Hardening v29.2 Hotfix

This hotfix updates the v29.1 router-hardening endpoint.

## Purpose

- Keep metadata/count questions out of broad source-truth fallback.
- Prefer `page_context_v2` for v2 summary coverage counts.
- Treat graph `Has_v2`, `HAS_CONTEXT`, and `SUMMARIZES` as diagnostic metadata signals, not proof authority.
- Resolve nomenclature page counts from graph paths such as:
  - `part -> HAS_NOMENCLATURE -> nomenclature`
  - `part -> APPEARS_ON -> page`
  - `page -> MENTIONS_PART -> part`
- Count unique pages for metadata questions.
- Keep graph/Leiden/nomenclature metadata as guidance only.

## Expected fixed behavior

- `how many pages have a v2 summary` should answer from `page_context_v2` when present.
- `how many pages mention a nomenclature` should use graph nomenclature edges if present.
- Neither query should return unrelated `covered_part_number` records.

## Safety contract

- No raw 5TB scan at query time.
- No graph rebuild at query time.
- No source-truth mutation.
- No Postgres/Qdrant/OpenSearch writes.
- Metadata and graph signals are guidance/count metadata only, not proof authority for part/manual relationships.
