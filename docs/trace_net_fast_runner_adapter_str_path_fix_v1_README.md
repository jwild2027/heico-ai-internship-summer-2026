# TRACE-Net fast runner adapter string-path fix v1

Fixes `trace_net_image_route_fast_chat_adapter_v1.build_adapter` so it accepts both `Path` and `str` values for `image_visual_evidence_pack` and `output_dir`. This matches how the main fast chat runner invokes the adapter through `_invoke_builder`.

Safety: no database writes, no vector/search writes, no source-truth mutation, no answer permission.
