# Page image quality stable compatibility fix

Replaces `tiff/page_image_recognition_quality.py` with a stable parser/checker that:

- preserves the public API expected by scripts and tests;
- reads current audit JSON shape;
- reads temporary graph overlay paths from tests rather than default artifacts;
- returns object-style `QualityCheck` entries;
- writes a JSON quality artifact suitable for the full-system wrapper.
