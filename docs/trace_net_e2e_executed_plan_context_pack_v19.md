# TRACE-Net E2E Executed Plan Context Pack v19

Builds live context packs from v18 dynamic plan execution records.

The v19 contract keeps proof and guidance separate:

- `SOURCE-TRUTH EVIDENCE` is the only proof authority for final claims.
- Leiden/community graph records are guidance only.
- v2 page summaries are guidance only.
- Capped/high-degree result sets disclose total vs returned counts and drill-down options.
- The LLM reads compact context packs only, not the raw corpus or entire graph.

This module does not call an LLM, rerun OCR, rebuild embeddings, rebuild graph, scan the raw source corpus, mutate source truth, or write to external services.
