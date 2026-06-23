# TRACE-Net table_line_geometry Paddle extraction bbox patch

## Module
`tiff/trace_net_table_line_geometry_v1.py`

## Purpose
The Paddle-style bbox resolver is now selected for 20/20 table geometry cards, and the legacy crop guard no longer blocks the morphology chooser. However, crop morphology still loses to page morphology because the page has weak or absent grid-line signal. This patch exposes the clean Paddle-style bbox as the table extraction bbox even when line morphology remains page-scoped.

## Safety
Local Python-source edit only. No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.
