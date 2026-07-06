# TRACE-Net Llama 3.2 Vision Image Route Summary v2

V2 fixes the first runner's bad discovery behavior.

Fixes:
- rejects fake page IDs such as metadata_page_000001 and source_p000001
- does not search using bare page numbers like 1, which matched unrelated preview images
- excludes table preview/overlay/contact-sheet paths by default
- prefers exact page-id image matches
- records and prints the actual error field
- keeps Engram-style engineering behavior guidance

Environment variables:
- TRACE_NET_VISION_MODEL=llama3.2-vision:11b
- TRACE_NET_MAX_IMAGE_PAGES=12
- TRACE_NET_IMAGE_ROOTS=local_data
- TRACE_NET_IMAGE_VISUAL_EVIDENCE_PACK=<path>
- TRACE_NET_ALLOW_PREVIEW_IMAGES=0
- TRACE_NET_OUTPUT_DIR=<path>
