import importlib.util
from pathlib import Path


def test_scripts_import_without_running():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/benchmark/ingestion/build_trace_net_dynamic_final_gate_execution_v1.py",
        "scripts/benchmark/check_trace_net_dynamic_final_gate_execution_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        assert hasattr(module, "main")
