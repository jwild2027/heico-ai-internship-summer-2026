import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build_trace_net_part_number_exact_retrieval_probe_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("build_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_build")


def test_check_script_imports():
    path = Path("scripts/check_trace_net_part_number_exact_retrieval_probe_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_check")
