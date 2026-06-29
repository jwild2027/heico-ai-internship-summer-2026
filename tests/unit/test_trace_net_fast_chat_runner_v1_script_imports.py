import importlib.util
from pathlib import Path


def test_run_script_imports():
    assert Path("scripts/run_trace_net_fast_chat_runner_v1.py").exists()
    spec = importlib.util.spec_from_file_location("run_trace_net_fast_chat_runner_v1", "scripts/run_trace_net_fast_chat_runner_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def test_check_script_imports():
    assert Path("scripts/check_trace_net_fast_chat_runner_v1_quality.py").exists()
    spec = importlib.util.spec_from_file_location("check_trace_net_fast_chat_runner_v1_quality", "scripts/check_trace_net_fast_chat_runner_v1_quality.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
