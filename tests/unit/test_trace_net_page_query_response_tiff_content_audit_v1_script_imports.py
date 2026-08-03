import importlib.util
from pathlib import Path


def test_build_script_importable():
    path = Path("scripts/build/ingestion/build_trace_net_page_query_response_tiff_content_audit_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_page_query_response_tiff_content_audit_v1", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_build")


def test_check_script_importable():
    path = Path("scripts/maintenance/benchmark/check_trace_net_page_query_response_tiff_content_audit_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_page_query_response_tiff_content_audit_v1_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_check")
