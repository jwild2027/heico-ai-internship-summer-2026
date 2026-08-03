# TRACE-Net Visual Question Context Adapter v1.2

Fixes aggregate-container and cross-page joins found in v1.1.

- Yields only scoped page/visual records.
- Never treats a top-level summary container as a page record.
- Requires direct canonical `page_id` on each record.
- Rejects visual IDs whose embedded page ID differs from the record page.
- No model calls, OCR, rerouting, writes, or answer permission.
