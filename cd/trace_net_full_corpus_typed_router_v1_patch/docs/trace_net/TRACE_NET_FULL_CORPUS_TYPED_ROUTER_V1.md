# TRACE-Net Full-Corpus Serving + Typed Query-Atom Router v1

## Scope

This patch implements two improvements:

1. Builds a new v27 serving manifest from existing OCR, table, part/nomenclature,
   V2/V3 summary, and Leiden/community JSON artifacts.
2. Replaces the front-door's three-keyword router decision with deterministic
   query-atom extraction while retaining compatible execution routes.

## Typed tunnels

- `exact_source_lookup`
- `table_exact_or_structured_retrieval`
- `visual_figure_retrieval`
- `guided_candidate_discovery`
- `procedure_warning_text_retrieval`
- `fast_clarification`
- `safety_authority_search`
- `general_source_truth_retrieval`

The public `route` remains compatible (`normal_ask`, `guided_discovery`, or
`gemma_confirmed_image_visual`). The new details are exposed under
`trace_net.router_decision` and `trace_net.retrieval_tunnel`.

## Safety

The builder is read-only. It does not scan TIFFs, run OCR, or write to
Postgres, Qdrant, or OpenSearch. Summaries and communities remain guidance;
they do not become proof.
