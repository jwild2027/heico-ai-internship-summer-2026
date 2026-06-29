# TRACE-Net Gold Label Review Workbook v1 visual clamp

This focused tuning patch makes canonical route suggestions more conservative for image/diagram pages.

It prevents generic IPL terms such as `Figure`, `Item`, and `CH-SEC-UN-FIG` from turning large numbers of parts-list/table pages into `image_visual_diagram`.

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.
