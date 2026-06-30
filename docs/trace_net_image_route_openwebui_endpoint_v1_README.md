# TRACE-Net Image Route OpenWebUI Endpoint v1

This module provides a standalone OpenAI-compatible endpoint wrapper for the now-integrated `image_or_diagram` fast-chat route.

It does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. It shells into `tiff/trace_net_fast_chat_runner_v1.py`, reads the resulting PASS artifact, and returns either `/v1/chat/completions` or `/api/trace-net/ask` JSON.

The endpoint is intentionally standalone so it can be smoke-tested before touching the existing live endpoint stack.
