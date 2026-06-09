# TRACE-Net Algorithm Policy

Status: **OK**
Policy version: `trace_net_algorithm_policy_v1`

## Summary

- `pages_loaded`: 509
- `projection_nodes`: 1856
- `projection_edges`: 12363
- `leiden_available`: True
- `best_repair_batching_algorithm`: route_grouping
- `best_repair_batching_score`: 0.959966
- `best_retrieval_expansion_algorithm`: leiden
- `best_retrieval_expansion_score`: 0.899821
- `leiden_vs_route_repair_delta`: -0.114817
- `leiden_vs_route_retrieval_delta`: 0.014623
- `policy_repair_batching_algorithm`: route_grouping
- `policy_retrieval_expansion_algorithm`: leiden
- `policy_source_trace_algorithm`: deterministic_graph_traversal

## Job Policy

| Job | Selected algorithm | Family | Score | Uses communities | Source of truth |
|---|---|---|---:|---:|---:|
| `broad_retrieval_expansion` | `leiden` | `semantic_neighborhood` | 0.899821 | True | False |
| `community_summaries` | `leiden` | `semantic_neighborhood` | 0.899821 | True | False |
| `cross_document_exploration_future` | `leiden` | `semantic_neighborhood` | 0.899821 | True | False |
| `exact_page_lookup` | `deterministic_graph_traversal` | `source_trace` | None | False | True |
| `exact_part_lookup` | `deterministic_graph_traversal` | `source_trace` | None | False | True |
| `review_queue_batching` | `route_grouping` | `operational_batching` | 0.959966 | False | False |
| `source_trace` | `deterministic_graph_traversal` | `source_trace` | None | False | True |
| `table_extraction_batching` | `route_grouping` | `operational_batching` | 0.959966 | False | False |
| `trace_net_repair_batching` | `route_grouping` | `operational_batching` | 0.959966 | False | False |

## Rationale

### `broad_retrieval_expansion`

Selected: `leiden`
Backup: `route_grouping`
Reason: Selected by best retrieval_expansion_score from community ablation metrics.
Notes:
- leiden retrieval score=0.899821
- selected retrieval score=0.899821
- Use only to expand candidates; every answer still needs deterministic source trace.

### `community_summaries`

Selected: `leiden`
Backup: `route_grouping`
Reason: Community summaries should use semantic neighborhoods; prefer Leiden when available.
Notes:
- Community summaries are exploration aids, not evidence proof.
- Each community summary must retain source page IDs.

### `cross_document_exploration_future`

Selected: `leiden`
Backup: `route_grouping`
Reason: Cross-document relatedness benefits from semantic communities once multiple documents exist.
Notes:
- Only relevant when more than one document/manual has been ingested.
- Use canonical bridge nodes like parts, ATA codes, topics, and traits.

### `exact_page_lookup`

Selected: `deterministic_graph_traversal`
Backup: `page_index_lookup`
Reason: Exact page lookup should resolve Page -> Document/ATA/Source/TIFF/OCR directly.
Notes:
- Exact source tracing must use deterministic graph traversal, not community expansion.
- Communities may suggest related neighborhoods but cannot prove source evidence.

### `exact_part_lookup`

Selected: `deterministic_graph_traversal`
Backup: `exact_keyword_catalog_lookup`
Reason: Exact part lookup needs source-proof paths through Part -> PartMention -> Page -> Source.
Notes:
- Exact source tracing must use deterministic graph traversal, not community expansion.
- Communities may suggest related neighborhoods but cannot prove source evidence.

### `review_queue_batching`

Selected: `route_grouping`
Backup: `leiden`
Reason: Human review should batch by repair route first; Leiden can be used inside a route for secondary grouping.
Notes:
- Primary grouping: route/trust/review traits.
- Secondary grouping: Leiden community inside each route when helpful.

### `source_trace`

Selected: `deterministic_graph_traversal`
Backup: `source_link_index_lookup`
Reason: Source evidence must remain deterministic and auditable.
Notes:
- Exact source tracing must use deterministic graph traversal, not community expansion.
- Communities may suggest related neighborhoods but cannot prove source evidence.

### `table_extraction_batching`

Selected: `route_grouping`
Backup: `route_grouping`
Reason: Table extraction follows explicit TRACE-Net routes and gates; route grouping is intentionally preferred.
Notes:
- Use table_high/table_medium/table_candidate_review/skip_non_table rather than Leiden for execution queues.
- Graph and layout gates remain the final check before cutting or OCR.

### `trace_net_repair_batching`

Selected: `route_grouping`
Backup: `deterministic_graph_traversal`
Reason: Selected by best repair_batching_score from community ablation metrics.
Notes:
- route_grouping repair score=0.959966
- selected repair score=0.959966
- Use this for queues like table extraction, cleanup repair, OCR validation, and human review batching.

## Rules

- **source_trace_never_uses_communities**: Exact page, part, and source-trace jobs use deterministic graph traversal regardless of community scores.
- **repair_uses_best_batching_metric**: TRACE-Net repair/review queues use the measured best repair-batching algorithm, currently route_grouping in the 509-page run.
- **retrieval_uses_best_expansion_metric**: Broad retrieval expansion uses the measured best retrieval-expansion algorithm, currently Leiden in the 509-page run.
- **communities_expand_candidates_only**: Leiden/other communities may expand candidates but cannot prove final answers without source-trace paths.
