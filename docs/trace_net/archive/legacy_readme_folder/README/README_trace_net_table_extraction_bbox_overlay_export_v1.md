# TRACE-Net Table Extraction BBox Overlay Export v1

Creates PNG overlay files for the table extraction bboxes emitted by `table_line_geometry`.

Green rectangle:
- `table_extraction_bbox`

Yellow rectangle:
- `table_region_bbox`

Safety:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
