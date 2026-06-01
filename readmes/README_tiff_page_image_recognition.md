# TIFF page image-recognition audit

This patch adds a lightweight local image-recognition layer for TIFF pages. It is intentionally not a full vision model. It uses page image features to classify pages as likely blank, table/grid, figure/diagram, image-heavy, or text/parts-list-like.

Run:

```bash
python scripts/audit_page_image_recognition.py --write-json --write-graph-overlay
```

Outputs:

```text
local_data/organization/image_recognition/page_image_recognition_audit.json
local_data/organization/image_recognition/image_recognition_graph_nodes.json
local_data/organization/image_recognition/image_recognition_graph_edges.json
```

The graph overlay is separate from the main graph by default. It can later be merged as:

```text
Page --HAS_IMAGE_ANALYSIS--> PageImageAnalysis
PageImageAnalysis --CLASSIFIED_AS_VISUAL--> VisualType
```

This complements OCR/context-based visual signals. Later, a true vision model can add table bounding boxes, figure regions, diagrams, and visual blank-page verification.
