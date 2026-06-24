# TRACE-Net E2E Live Relationship Final-Gated Endpoint v31

v31 wires the v30 relationship final gate directly into the live WebUI endpoint path.

Pipeline:

1. v29.2 router handles deterministic lookup/listing/metadata/relationship routing.
2. v30 relationship final gate validates the answer before it leaves the endpoint.
3. WebUI receives only the final-gated answer.

Safety contract:

- Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only.
- Direct source-truth evidence is required for factual relationship claims.
- The endpoint does not scan raw 5TB data, rebuild graph, mutate source truth, or write to services.
- Unsafe relationship wording is repaired before user-visible output.
