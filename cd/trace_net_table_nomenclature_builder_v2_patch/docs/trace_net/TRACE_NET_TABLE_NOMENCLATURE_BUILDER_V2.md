# TRACE-Net Table/Nomenclature Builder v2

This patch improves the full-corpus serving builder and table-text matcher.

## Fixes

- Prioritizes high-value artifacts during discovery, including guided discovery,
  source citations, graph explorer, page-context overlay, and nomenclature files.
- Extracts `candidate_part_number`, `nomenclature`, graph nomenclature nodes, and
  source/citation/retrieval text fields.
- Duplicates nomenclature into `table_text` so table/IPL queries can find entries
  such as `RING, LOCKING`.
- Adds token-order-insensitive table text matching so `LOCKING RING` can match
  source text written as `RING, LOCKING`.
- Keeps exact part-number matching strict; fuzzy matching is only for table text.

## Safety

No OCR, TIFF scanning, database writes, or source-truth mutation.
