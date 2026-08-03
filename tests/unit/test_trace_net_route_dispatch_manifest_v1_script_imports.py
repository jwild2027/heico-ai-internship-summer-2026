def test_script_imports() -> None:
    import scripts.build.ingestion.build_trace_net_route_dispatch_manifest_v1 as build_script
    import scripts.maintenance.benchmark.check_trace_net_route_dispatch_manifest_v1_quality as check_script

    assert build_script.main is not None
    assert check_script.main is not None
