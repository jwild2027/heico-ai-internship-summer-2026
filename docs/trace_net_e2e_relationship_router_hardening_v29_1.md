# TRACE-Net E2E Relationship Router Hardening v29.1

This module hardens the v29 relationship endpoint against metadata/count routing failures.

## Purpose

v29.1 routes metadata and field-count questions before broad source-truth fallback. This prevents questions such as:

- `how many pages have a v2 summary`
- `how many pages mention a nomenclature`

from incorrectly returning unrelated covered part number records.

## Graph signals

When available, the module searches existing graph artifacts for relationship labels such as:

- `Has_v2`
- `has_v2`
- `Has_nomenclature`
- `Has_nomeclature`

These signals are metadata/navigation guidance only. They are not source-truth proof for technical claims.

## Contracts

- Source-truth records remain the only proof authority for factual source claims.
- V2 summaries are guidance/compression metadata only.
- Graph Has_v2 / Has_nomenclature signals are count/navigation metadata only.
- Unknown metadata/field questions return audit-only instead of broad noisy matches.
- Query-time execution does not scan raw 5TB data, rebuild the graph, rerun OCR, mutate source truth, or write to services.

## Expected behavior

- `how many pages have a v2 summary` returns an artifact metadata count.
- `how many pages mention a nomenclature` returns a graph/field count if supported, otherwise audit-only.
- `Find part number DOES-NOT-EXIST-999` returns audit-only.
- `What pages are related to part number 120-36833-503?` returns graph/Leiden guidance only and requires source-truth confirmation before relationship claims.
