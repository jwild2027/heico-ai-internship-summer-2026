# TRACE-Net E2E Live Deterministic Answer Planner + Drilldown v28

v28 extends the v27 stage-timing fast path with explicit deterministic response modes and source-truth drill-down support.

Response modes:

- `exact_single_value`
- `exact_missing_value`
- `field_listing`
- `capped_listing`
- `drilldown_request`
- `relationship_or_synthesis_needs_llm`

The endpoint skips the LLM for deterministic source-truth answer classes and reserves Gemma for relationship/synthesis questions. Source-truth evidence remains the only proof authority; graph/Leiden, v2 summaries, nearby OCR, and aggregation metadata remain guidance/disclosure only.

## v28.1 polish and metadata hotfix

This hotfix keeps the endpoint version at v28 but tightens demo/readiness behavior:

- Polishes deterministic answer whitespace, including citation spacing and joined words such as `doesnot` and `onlyand`.
- Preserves strict-filter audit metadata:
  - `raw_candidate_match_count`
  - `target_unique_match_count`
  - `target_occurrence_count`
  - `collapsed_duplicate_record_count`
- Keeps missing exact values audit-only, with no broad/noisy fallback matches.
- Keeps final answers rebuilt from source-truth evidence only.
- Does not call the LLM for deterministic response modes.
