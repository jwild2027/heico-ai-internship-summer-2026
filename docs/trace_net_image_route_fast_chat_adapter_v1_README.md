# TRACE-Net Image Route Fast Chat Adapter v1

This module turns the image visual evidence pack into a fast-chat-shaped image route response for `image_or_diagram` questions.

Authority model:

- LLaVA and OCR visual observations are navigation/guidance.
- Trusted OCR/table/figure-item evidence is required before a part number identity can be stated.
- MEDIUM visual links can produce limited cited answers.
- LOW visual/OCR-only observations remain review-only.
- The adapter does not grant answer permission, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

Typical input:

`local_data/organization/trace_net/image_visual_evidence_pack_v1/trace_net_image_visual_evidence_pack_v1.json`

Typical output:

`local_data/organization/trace_net/image_route_fast_chat_adapter_v1/trace_net_image_route_fast_chat_adapter_v1.json`
