import importlib


def test_script_and_module_imports():
    assert importlib.import_module("tiff.trace_net_table_full_enclosure_bbox_reconstructor_v1")
    assert importlib.import_module("tiff.trace_net_table_full_enclosure_bbox_reconstructor_v1_quality")
