import importlib


def test_module_imports() -> None:
    module = importlib.import_module("tiff.trace_net_element_category_taxonomy_v1")
    assert hasattr(module, "build_element_category_taxonomy")
    assert hasattr(module, "quality_report")


def test_script_modules_import() -> None:
    assert importlib.import_module("scripts.build.ingestion.build_trace_net_element_category_taxonomy_v1")
    assert importlib.import_module("scripts.maintenance.benchmark.check_trace_net_element_category_taxonomy_v1_quality")
