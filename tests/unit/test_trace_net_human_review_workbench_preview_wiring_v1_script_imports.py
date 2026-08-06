from __future__ import annotations


def test_scripts_import() -> None:
    import scripts.build.ingestion.build_trace_net_human_review_workbench_preview_wiring_v1 as build_script
    import scripts.maintenance.ingestion.check_trace_net_human_review_workbench_preview_wiring_v1_quality as check_script

    assert callable(build_script.main)
    assert callable(check_script.main)
