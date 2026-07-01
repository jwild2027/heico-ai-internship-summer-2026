# TRACE-Net Image Visual Summary v1 Semantic Signature Fix

Fixes a semantic-validator integration regression where `build_image_visual_summary()` passed `ocr_text_lookup` into `_visual_summary_card()`, but the card builder signature did not accept it.

Safety: artifact-only; no Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, no answer permission.
