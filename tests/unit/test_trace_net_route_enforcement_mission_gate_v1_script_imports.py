def test_route_enforcement_mission_gate_scripts_import() -> None:
    import scripts.build.ingestion.build_trace_net_route_enforcement_mission_gate_v1  # noqa: F401
    import scripts.maintenance.s6_retrieval.check_trace_net_route_enforcement_mission_gate_v1_quality  # noqa: F401
