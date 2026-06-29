def test_scripts_import():
    import scripts.build_trace_net_four_route_storage_gate_v1 as build_script
    import scripts.check_trace_net_four_route_storage_gate_v1_quality as check_script

    assert build_script.main_build
    assert check_script.main_quality
