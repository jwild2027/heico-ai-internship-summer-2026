# TRACE-Net Engineering Query Planner v1

Builds a guidance-aware route plan for broad engineering questions.

This module consumes the v2 summary guidance index and produces a structured plan containing:

- extracted entities such as figures, items, part numbers, and topics;
- task type classification;
- required and optional TRACE-Net routes;
- guidance pages from v2 summaries;
- proof requirements;
- forbidden claims;
- safety counters.

V2 summaries are always marked as guidance only. They may guide route selection and answer framing, but they may not prove final factual claims.

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.

## H2B strict guidance behavior

For specific entity questions (figure, item/callout, exact part number, or part family), the planner no longer backfills `guidance_pages` with generic illustrated-parts-list or maintenance-manual summaries. V2 summaries are selected only when they contain a strong exact entity hint such as `figure_hint:<figure>` or `part_hint:<part number>`. If no exact entity guidance exists, the planner returns an empty guidance list and still plans proof routes.

This preserves the rule that summaries guide route planning only when relevant; they never prove the answer.
