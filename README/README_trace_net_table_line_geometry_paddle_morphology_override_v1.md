# TRACE-Net table_line_geometry Paddle morphology override patch

## Module
`tiff/trace_net_table_line_geometry_v1.py`

## Purpose
The Paddle-style bbox resolver is already selected for 20/20 table cards, but the legacy crop-completeness guard still blocks crop morphology and forces page morphology. This patch preserves legacy guard fields for audit while allowing morphology selection to evaluate the clean Paddle-style selected bbox.

## Files
- `apply_trace_net_table_line_geometry_paddle_morphology_override_v1.py`
- `README_trace_net_table_line_geometry_paddle_morphology_override_v1.md`

## Safety
This patch only edits Python source locally. It does not write Postgres, Qdrant, or OpenSearch. It does not mutate source truth and does not grant answer permission.
