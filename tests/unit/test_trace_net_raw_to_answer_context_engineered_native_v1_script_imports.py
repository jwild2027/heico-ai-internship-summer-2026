import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/operations/validation/run_trace_net_raw_to_answer_context_engineered_native_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("run_ctx", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)


def test_check_script_imports():
    path = Path("scripts/maintenance/validation/check_trace_net_raw_to_answer_context_engineered_native_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_ctx", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
