# TRACE-Net E2E LLM-Assisted Query Planner v17

This module adds the first structured planning contract for future LLM-assisted TRACE-Net retrieval.

It does **not** call an LLM yet. Instead, it defines the validated plan shape that a future LLM planner must produce and that TRACE-Net must validate before execution.

## Core contract

- The LLM may propose structured query plans, subqueries, synonyms, and graph expansion hints.
- TRACE-Net validates every plan before execution.
- TRACE-Net executes only allowed tunnels.
- v2 page summaries are guidance only.
- Leiden communities are graph/navigation guidance only.
- Source-truth evidence is required for final factual claims.
- Query-time planning must not scan raw 5TB source data.
- The LLM reads a compact context pack, not the whole graph or source corpus.

## Tunnel authority

Source-truth/proof tunnel:

- `table_exact_search_tunnel`

Ranking support tunnels:

- `table_hybrid_bridge_tunnel`
- `qdrant_page_profile_tunnel`

Guidance-only tunnels:

- `page_summary_tunnel`
- `graph_community_tunnel`
- `graph_navigation_tunnel`
- `route_metadata_tunnel`
- `table_route_summary_tunnel`

## Why this matters

A pure hard-coded planner would be too narrow. A pure LLM planner would be too unsafe. v17 establishes the middle path: LLM-assisted planning with deterministic TRACE-Net validation and tunnel authority rules.
