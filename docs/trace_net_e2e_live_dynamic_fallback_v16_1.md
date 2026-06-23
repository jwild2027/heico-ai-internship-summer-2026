# TRACE-Net E2E Live Dynamic Fallback v16.1 Hotfix

Fixes v16 build quality where probe selection could include an unsupported exact fallback probe and exact covered-part queries could return too few related citations for the configured quality gate.

The hotfix keeps the safety contract unchanged: it uses prebuilt exact-search evidence only, does not call an LLM, does not rerun OCR/embeddings/graph/table extraction, does not mutate source truth, and does not write to services.
