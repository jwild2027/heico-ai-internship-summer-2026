import importlib


def test_script_imports():
    assert importlib.import_module("tiff.trace_net_table_route_value_audit_v1")
    assert importlib.import_module("tiff.trace_net_table_route_value_audit_v1_quality")
