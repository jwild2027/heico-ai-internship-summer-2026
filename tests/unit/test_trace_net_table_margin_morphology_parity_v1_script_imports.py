import importlib


def test_script_modules_import():
    assert importlib.import_module("tiff.trace_net_table_margin_morphology_parity_v1")
    assert importlib.import_module("tiff.trace_net_table_margin_morphology_parity_v1_quality")
