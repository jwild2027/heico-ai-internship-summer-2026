# TRACE-Net E2E Query Planning Routing v1

This module sits between `trace_net_e2e_query_input_v1` and the hybrid retrieval runtime.
It adds explicit query planning and query routing records.

The key idea is that graph/source-trace records and summary/profile records act as **tunnels**:

- graph/source-trace tunnels move a query toward page/source/citation neighborhoods;
- page/profile summary tunnels move free-text queries toward likely pages;
- table-route summary tunnels move part/manual/table terms toward table evidence cards;
- visual summary tunnels move IPL/diagram-like queries toward visual/callout candidates.

These tunnels are routing and ranking helpers only. They cannot answer directly, prove claims,
mutate source truth, or write to Postgres, Qdrant, OpenSearch, or live upload paths.

The output keeps `query_records` compatible with the existing E2E hybrid retrieval runtime, but
adds `query_routing_plan` and `query_tunnels` fields for future runtime modules.
