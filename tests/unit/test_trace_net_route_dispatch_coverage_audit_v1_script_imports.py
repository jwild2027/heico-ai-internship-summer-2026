from __future__ import annotations


def test_script_imports() -> None:
    import scripts.build.ingestion.build_trace_net_route_dispatch_coverage_audit_v1 as build_script
    import scripts.maintenance.benchmark.check_trace_net_route_dispatch_coverage_audit_v1_quality as check_script

    assert callable(build_script.main)
    assert callable(check_script.main)
