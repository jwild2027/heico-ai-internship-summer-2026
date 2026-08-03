import importlib.util
from pathlib import Path


def test_run_script_imports() -> None:
    path = Path("scripts/operations/ingestion/run_trace_net_it_issue_origin_test_matrix_v1.py")
    spec = importlib.util.spec_from_file_location("run_trace_net_it_issue_origin_test_matrix_v1", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports() -> None:
    path = Path("scripts/maintenance/benchmark/check_trace_net_it_issue_origin_test_matrix_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_it_issue_origin_test_matrix_v1_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
