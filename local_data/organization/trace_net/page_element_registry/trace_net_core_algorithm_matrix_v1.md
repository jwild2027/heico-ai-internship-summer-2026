# TRACE-Net Core Algorithm Matrix v1

| TRACE-Net step | Does current code do it? | Status |
|---|---:|---|
| Page enters system | Yes | Registry represents 509 page(s); source trace pages: 509. |
| Classify page traits | Yes | Registry emits deterministic traits for 509 page(s). Trait families include OCR, source, table/list, figure/chart, part/catalog, context, and revision/front-matter signals. |
| Choose extraction route | Yes | Registry emits recommended extraction routes for 509 page(s), including source, OCR, part, table, visual, context, consensus, trust, and graph-attachment routes. |
| Run specialized extractors | Yes for current extractor outputs; registry plans next routes | Existing artifacts provide OCR/source/part/table/visual/context outputs. Registry does not rerun extractors; it records which existing outputs are present and which route should run next. |
| Retry failures through fishnet layers | Planner implemented; universal executor future | Registry emits fishnet retry plans for 509 page(s). It is plan-only and does not mutate source truth. |
| Compare outputs against OCR/catalog/graph | Yes | Registry emits comparison targets for 509 page(s), including OCR, catalog/part graph, source trace, citations, table/visual signals, RAG eligibility, and trust authority where relevant. |
| Assign trust tier | Yes | Registry attaches trust assignment policy to 509 page(s): evidence_consensus_then_trust_authority_gate. |
| Attach clean evidence to graph | Plan generated; Postgres writeback remains explicit | Registry emits graph attachment plans for 509 page(s). Plans are read-only and prepare Page -> Element/Evidence/Citation relationships. |
