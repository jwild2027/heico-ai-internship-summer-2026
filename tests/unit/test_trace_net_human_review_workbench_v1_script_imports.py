import importlib.util
from pathlib import Path


def test_scripts_importable():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build/ingestion/build_trace_net_human_review_workbench_v1.py",
        "scripts/maintenance/ingestion/check_trace_net_human_review_workbench_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
