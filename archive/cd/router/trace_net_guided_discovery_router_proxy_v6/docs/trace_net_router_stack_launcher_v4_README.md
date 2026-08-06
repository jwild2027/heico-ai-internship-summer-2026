# TRACE-Net Router Stack Launcher v4

Launcher v4 starts the same three local services as earlier stack launchers, but uses router/proxy v6 on port 8017.

Services:

1. Normal TRACE-Net ask endpoint on 8014
2. Guided candidate discovery endpoint on 8016
3. Router/proxy v6 endpoint on 8017

Web UI target:

- Base URL: `http://127.0.0.1:8017/v1`
- Model: `trace-net-router-proxy-v6`

Safety contract: process launcher only; no source-truth mutation and no database/index writes.
