from pathlib import Path
import importlib.util


def test_build_script_importable():
    path = Path("scripts/build/graph/build_trace_net_llm_graph_path_response_guard_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("build_trace_net_llm_graph_path_response_guard_v1", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_build")


def test_check_script_importable():
    path = Path("scripts/maintenance/validation/check_trace_net_llm_graph_path_response_guard_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_trace_net_llm_graph_path_response_guard_v1_quality", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main_check")
