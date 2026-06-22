# TRACE-Net E2E Local Endpoint Formatter Hotfix v3

Fixes a remaining WebUI display typo where upstream smoke response text could render `ont_p_...` instead of `on t_p_...`.

Also keeps the citation value repair from v2 intact so OpenAI-compatible responses render citation values such as `value=120-36833-001`.

Safety contract unchanged: no answer authority, no claim-proof authority, no source-truth mutation, and no Postgres/Qdrant/OpenSearch writes.
