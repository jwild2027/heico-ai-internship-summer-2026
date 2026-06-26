import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build_trace_net_fishnet_route_signal_workbench_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("build_trace_net_fishnet_route_signal_workbench_v1", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_build")


def test_quality_script_imports():
    path = Path("scripts/check_trace_net_fishnet_route_signal_workbench_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_trace_net_fishnet_route_signal_workbench_v1_quality", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_check")
