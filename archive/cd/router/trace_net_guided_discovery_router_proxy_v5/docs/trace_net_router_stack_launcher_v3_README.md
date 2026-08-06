# TRACE-Net router stack launcher v3

Starts the same local three-service stack as v2, but points the web UI router to `serve_trace_net_guided_discovery_router_proxy_v5.py` and model `trace-net-router-proxy-v5`.

Services:
- 8014 normal TRACE-Net endpoint
- 8016 guided candidate discovery endpoint
- 8017 router/proxy endpoint

Safety contract: process launcher only; no source-truth mutation or database writes.
