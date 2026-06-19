import importlib


def test_modules_import():
    assert importlib.import_module("tiff.trace_net_table_full_region_recovery_v1")
    assert importlib.import_module("tiff.trace_net_table_full_region_recovery_v1_quality")
