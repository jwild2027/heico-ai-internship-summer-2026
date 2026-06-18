def test_script_imports():
    import scripts.build_trace_net_table_line_geometry_route_contract_audit_v1 as build_script
    import scripts.check_trace_net_table_line_geometry_route_contract_audit_v1_quality as check_script

    assert build_script.main
    assert check_script.main
