from __future__ import annotations


def test_script_modules_import() -> None:
    import scripts.build.ingestion.build_trace_net_page_ink_route_evidence_v1 as build_script
    import scripts.maintenance.benchmark.check_trace_net_page_ink_route_evidence_v1_quality as check_script

    assert build_script.main is not None
    assert check_script.main is not None
