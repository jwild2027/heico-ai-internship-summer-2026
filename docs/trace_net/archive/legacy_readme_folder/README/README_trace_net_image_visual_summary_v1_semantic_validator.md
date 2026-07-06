# TRACE-Net Image Visual Summary v1 Semantic Validator

Adds conservative semantic validation to LLaVA visual-observation cards.

The validator cross-checks visible labels/callouts against fishnet OCR text, detects likely hallucinated label patterns such as `Item 1` through `Item 99`, marks generic visual labels as low value, and separates WebUI-allowed visual context from review-only vision guesses.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- vision output remains retrieval/review guidance only
