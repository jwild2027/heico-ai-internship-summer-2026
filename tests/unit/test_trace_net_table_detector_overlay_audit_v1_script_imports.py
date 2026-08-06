import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build/tables/build_trace_net_table_detector_overlay_audit_v1.py")
    spec = importlib.util.spec_from_file_location("build_overlay_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports():
    path = Path("scripts/maintenance/s2_ocr/check_trace_net_table_detector_overlay_audit_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_overlay_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
