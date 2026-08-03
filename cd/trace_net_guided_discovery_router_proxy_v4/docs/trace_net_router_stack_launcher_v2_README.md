# TRACE-Net router stack launcher v2

Starts the normal endpoint, guided discovery endpoint, and router/proxy with one command.

This v2 launcher uses `serve_trace_net_guided_discovery_router_proxy_v4.py`, so the web UI receives the improved guided-discovery routing for clue-only part lookup questions.

Safety contract: process launcher only; no writes to source truth, Postgres, Qdrant, or OpenSearch.
