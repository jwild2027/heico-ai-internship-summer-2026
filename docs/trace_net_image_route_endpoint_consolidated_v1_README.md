# TRACE-Net Image Route Endpoint Consolidation v1

This patch replaces the endpoint smoke/runtime module with one clean implementation.
It calls the existing image route fast-chat adapter directly, validates the same
source-trace/citation/safety counters, and writes an endpoint smoke manifest for
OpenWebUI testing.

It does not rerun LLaVA and does not mutate source truth or write to external stores.
