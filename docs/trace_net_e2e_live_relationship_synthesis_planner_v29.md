# TRACE-Net E2E Live Relationship/Synthesis Planner v29

v29 sits behind the v28 deterministic planner. It keeps exact lookup, listing, and drill-down questions deterministic and fast, while adding a guarded relationship/synthesis path for graph, Leiden, related-page, neighbor, and connection-style questions.

## Safety contract

- Source-truth evidence is the only proof authority.
- Graph/Leiden and v2 summaries are guidance only.
- Source-truth seed evidence proves only the seed facts, not inferred relationships.
- The LLM may draft relationship synthesis, but TRACE-Net rebuilds and final-gates the final answer.
- No query-time raw 5TB scan, graph rebuild, OCR rerun, source-truth mutation, or service write is allowed.

## Response modes

- Existing v28 deterministic modes remain active for lookup/listing/drill-down.
- `relationship_navigation` lists source-truth seed evidence plus graph/Leiden candidate pages for inspection.
- `relationship_synthesis` allows the LLM to draft over compact guidance, but the final answer explicitly avoids proving relationships from graph guidance alone.
- Missing relationship seeds return audit-only.

## Example questions

```text
What pages are related to part number 120-36833-503?
Which pages are in the same Leiden community as page t_p_120_1176_p000003?
Show graph neighbors for page t_p_120_1176_p000003
Explain how part number 120-36833-503 relates to manual reference 25-21-00
```

## Open WebUI

Use:

```text
Base URL: http://host.docker.internal:8024/v1
API Key: trace-net-local
Model: trace-net-e2e-live-relationship-synthesis-gemma-v29
```
