import importlib.util
from pathlib import Path


def _load_script(path: str):
    full = Path(path)
    spec = importlib.util.spec_from_file_location(full.stem, full)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_script_imports():
    module = _load_script("scripts/build_trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py")
    assert hasattr(module, "main_build")


def test_check_script_imports():
    module = _load_script("scripts/check_trace_net_engineering_webui_answer_server_v1_3_bridge_v1_quality.py")
    assert hasattr(module, "main_check")


def test_run_script_imports():
    module = _load_script("scripts/run_trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py")
    assert hasattr(module, "main_run")
