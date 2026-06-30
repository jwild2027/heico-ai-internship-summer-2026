# TRACE-Net Raw OCR Nomenclature Window Extractor v1

Extracts official-looking part nomenclature from raw OCR scan-pack text windows for already-linked image/visual part evidence.

Authority model:
- Visual evidence supplies linked figure/page/part anchors.
- Raw OCR text supplies candidate nomenclature windows.
- The module does not grant answer permission and does not mutate source truth.

Rejected values include part-number-only strings, filenames, booleans, page titles, graph/community labels, quantities, and OCR-only noise.
