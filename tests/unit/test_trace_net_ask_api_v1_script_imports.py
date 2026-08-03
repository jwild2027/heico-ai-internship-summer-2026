import importlib.util
from pathlib import Path


def test_run_script_imports() -> None:
    path = Path("scripts/operations/serving/run_trace_net_ask_api_v1.py")
    spec = importlib.util.spec_from_file_location("run_trace_net_ask_api_v1", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_check_script_imports() -> None:
    path = Path("scripts/maintenance/benchmark/check_trace_net_ask_api_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_ask_api_v1_quality", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
