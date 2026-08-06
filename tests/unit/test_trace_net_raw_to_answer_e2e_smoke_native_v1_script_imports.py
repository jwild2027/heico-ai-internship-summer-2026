import importlib.util
from pathlib import Path


def test_scripts_importable():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/benchmark/validation/run_trace_net_raw_to_answer_e2e_smoke_native_v1.py",
        "scripts/benchmark/validation/check_trace_net_raw_to_answer_e2e_smoke_native_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
