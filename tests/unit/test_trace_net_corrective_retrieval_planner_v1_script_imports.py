import importlib.util
from pathlib import Path


def test_build_script_importable():
    path = Path("scripts/build_trace_net_corrective_retrieval_planner_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_corrective_retrieval_planner_v1", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)


def test_check_script_importable():
    path = Path("scripts/check_trace_net_corrective_retrieval_planner_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_corrective_retrieval_planner_v1_quality", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
