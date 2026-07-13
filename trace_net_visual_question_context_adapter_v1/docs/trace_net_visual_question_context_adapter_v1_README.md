# TRACE-Net Visual Question Context Adapter v1

Read-only consolidation over existing TRACE-Net image-route artifacts. This module does not rerun LLaVA, OCR, route dispatch, callout extraction, region detection, or retrieval indexing.

It discovers JSON/JSONL artifacts, groups records by `page_id`, normalizes existing object descriptions, part/ATA/figure/callout identifiers, OCR-versus-vision fields, proof status, and `page_context_v2`, and preserves per-field provenance.

The generated context remains candidate-only by default and never grants final-answer permission or writes to Postgres, Qdrant, OpenSearch, or source truth.
