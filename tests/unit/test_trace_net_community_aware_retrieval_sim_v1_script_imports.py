import importlib.util
from pathlib import Path


def test_run_script_imports() -> None:
    path = Path("scripts/benchmark/s3_graph_store/run_trace_net_community_aware_retrieval_sim_v1.py")
    spec = importlib.util.spec_from_file_location("run_trace_net_community_aware_retrieval_sim_v1", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)


def test_check_script_imports() -> None:
    path = Path("scripts/benchmark/s3_graph_store/check_trace_net_community_aware_retrieval_sim_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_community_aware_retrieval_sim_v1_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
