import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/benchmark/s6_retrieval/build_trace_net_retrieval_payload_audit_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("build_trace_net_retrieval_payload_audit_v1", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert hasattr(module, "main_build")


def test_check_script_imports():
    path = Path("scripts/benchmark/s6_retrieval/check_trace_net_retrieval_payload_audit_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_trace_net_retrieval_payload_audit_v1_quality", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert hasattr(module, "main_check")
