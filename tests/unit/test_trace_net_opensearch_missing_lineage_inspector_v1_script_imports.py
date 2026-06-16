import importlib


def test_module_imports():
    module = importlib.import_module("tiff.trace_net_opensearch_missing_lineage_inspector_v1")
    assert callable(module.main)
    assert callable(module.build_missing_lineage_inspection)


def test_script_wrappers_import():
    build_script = importlib.import_module("scripts.build_trace_net_opensearch_missing_lineage_inspector_v1")
    check_script = importlib.import_module("scripts.check_trace_net_opensearch_missing_lineage_inspector_v1_quality")
    assert callable(build_script.main)
    assert callable(check_script.main)
