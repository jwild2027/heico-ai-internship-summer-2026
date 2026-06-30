# TRACE-Net Image Route Inventory + LLaVA Jobs v1

Patch A for the TRACE-Net image/visual route.

## Purpose

`trace_net_image_route_inventory_llava_jobs_v1` inventories pages that are routed to image/diagram/visual processing, verifies source trace fields, checks whether LLaVA visual summaries already exist, and writes a JSONL job manifest for missing LLaVA summaries.

## Authority model

LLaVA sees/describes visual content. OCR/table/figure-item evidence proves text and part identity. Graph/Leiden connects related context. TRACE-Net gates. Fast composers or Gemma answer only after evidence is packaged.

This patch does not call LLaVA. It only prepares source-traced, dry-run-safe jobs.

## Main outputs

- `trace_net_image_route_inventory_llava_jobs_v1.json`
- `trace_net_image_route_inventory_llava_jobs_v1_quality_check.json`
- `trace_net_image_route_inventory_llava_jobs_v1_jobs.jsonl`
- `trace_net_image_route_inventory_llava_jobs_v1_records.csv`
- `README_trace_net_image_route_inventory_llava_jobs_v1.md`

## Safety contract

No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.
