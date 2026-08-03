import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build/tables/build_trace_net_table_crop_completeness_guard_v1.py")
    spec = importlib.util.spec_from_file_location("build_crop_completeness", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_check_script_imports():
    path = Path("scripts/maintenance/benchmark/check_trace_net_table_crop_completeness_guard_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_crop_completeness", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
