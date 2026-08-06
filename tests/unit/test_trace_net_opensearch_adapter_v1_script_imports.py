import importlib.util
from pathlib import Path


def test_script_imports():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build/retrieval/build_trace_net_opensearch_adapter_v1.py",
        "scripts/maintenance/s6_retrieval/check_trace_net_opensearch_adapter_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
