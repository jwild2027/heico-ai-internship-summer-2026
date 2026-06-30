# TRACE-Net Image Visual Evidence Pack v1

Patch C packager for image-route evidence. It consumes `trace_net_visual_callout_table_linker_v2` and emits citation-labelled `V#` records. Linked MEDIUM/HIGH records can support limited image/diagram answers; LOW records are kept as review-only visual/OCR observations.

Safety contract: no Postgres/Qdrant/OpenSearch writes, no source-truth mutation, no answer permission.
