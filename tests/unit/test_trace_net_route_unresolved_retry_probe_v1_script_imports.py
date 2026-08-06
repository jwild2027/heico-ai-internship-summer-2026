import importlib


def test_scripts_import():
    assert importlib.import_module("scripts.build.ingestion.build_trace_net_route_unresolved_retry_probe_v1")
    assert importlib.import_module("scripts.maintenance.s6_retrieval.check_trace_net_route_unresolved_retry_probe_v1_quality")
