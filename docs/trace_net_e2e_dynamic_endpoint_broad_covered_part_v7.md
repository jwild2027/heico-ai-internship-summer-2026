# TRACE-Net E2E Dynamic Endpoint Broad Covered-Part Query Fix v7

Fixes a live WebUI dynamic-query routing issue where broad questions such as `What maintenance manual pages mention covered part numbers?` were classified as `table_text` because they contained the phrase `maintenance manual`.

The endpoint now routes broad `covered part number(s)` questions to the `covered_part_number` lane even when no concrete part-number token is present. This keeps the response focused on covered-part evidence instead of generic IPL table text.

Safety contract is unchanged: no answer permission, no proof authority, no source-truth mutation, and no OCR/embedding/summary/graph rebuilds at query time.
