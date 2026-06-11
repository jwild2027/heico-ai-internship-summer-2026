import importlib.util
from pathlib import Path


def test_build_script_imports() -> None:
    path = Path("scripts/build_trace_net_incremental_orchestrator_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_incremental_orchestrator_v1", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")


def test_quality_script_imports() -> None:
    path = Path("scripts/check_trace_net_incremental_orchestrator_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_incremental_orchestrator_v1_quality", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "quality_main")
