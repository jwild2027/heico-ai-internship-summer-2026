# TRACE-Net Visual Callout Table Linker v2

Patch B3 linker upgrade. It combines LLaVA observations, OCR figure/callout labels, OCR page text, and trusted table evidence. It rebuilds table rows from cell-level records, suppresses bad filename descriptions, and only upgrades confidence when trusted evidence supports the link.

Confidence rules:

- HIGH: figure + callout/item + same/nearby trusted row uniquely match.
- MEDIUM: figure/page or callout/page trusted row uniquely matches but the label match is partial.
- LOW: visual/OCR label only, ambiguous match, or no trusted proof.

Safety: no writes to Postgres/Qdrant/OpenSearch, no source-truth mutation, no answer permission.
