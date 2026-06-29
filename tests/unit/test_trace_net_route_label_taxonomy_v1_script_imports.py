import importlib


def test_script_imports():
    assert importlib.import_module("scripts.build_trace_net_route_label_taxonomy_v1")
    assert importlib.import_module("scripts.check_trace_net_route_label_taxonomy_v1_quality")
