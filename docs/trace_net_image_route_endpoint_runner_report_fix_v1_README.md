# TRACE-Net Image Route Endpoint Runner Report Fix v1

This patch hardens the image-route OpenWebUI endpoint wrapper. The underlying fast chat runner is source of truth. The wrapper now discovers the actual `trace_net_fast_chat_runner_v1.json` report even if the runner writes it inside a nested output folder, and exposes stdout/stderr tails for diagnosis when no report is found.

Safety: no database writes, no vector/search writes, no source-truth mutation, and no answer permission.
