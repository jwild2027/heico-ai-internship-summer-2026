import importlib


def test_script_and_quality_modules_import():
    assert importlib.import_module("tiff.trace_net_table_presence_verifier_v1")
    assert importlib.import_module("tiff.trace_net_table_presence_verifier_v1_quality")
    assert importlib.import_module("scripts.build_trace_net_table_presence_verifier_v1")
    assert importlib.import_module("scripts.check_trace_net_table_presence_verifier_v1_quality")
