# TRACE-Net Table Line Geometry Route Contract Audit v1

Audits existing `trace_net_table_line_geometry_v1` output against the route dispatch processor contract.

This is the first table-stack integration checkpoint before changing the table line geometry builder itself.

It verifies that every existing table geometry card is allowed by `trace_net_route_dispatch_processor_contract_v1`.

The module is read-only and does not grant answer permission or mutate source truth.
