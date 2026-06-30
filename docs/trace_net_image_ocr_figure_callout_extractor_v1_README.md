# TRACE-Net Image OCR Figure/Callout Extractor v1

Patch B3 image-route module. It reads exact visible manual labels from OCR for image-route pages, especially figure and item/callout labels. The extractor does not prove part identity and does not grant answer permission; it supplies safer labels for the visual linker.

Authority model:

- OCR reads exact visible labels such as `FIG. 69` and `ITEM 1`.
- LLaVA remains a visual observer.
- Trusted table/OCR/figure-item evidence still proves part identity.
- No Postgres/Qdrant/OpenSearch writes, no source-truth mutation, no answer permission.
