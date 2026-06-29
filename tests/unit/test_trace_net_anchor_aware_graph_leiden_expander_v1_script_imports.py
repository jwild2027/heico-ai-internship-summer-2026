import importlib.util
from pathlib import Path


def test_build_and_check_scripts_import():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build_trace_net_anchor_aware_graph_leiden_expander_v1.py",
        "scripts/check_trace_net_anchor_aware_graph_leiden_expander_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
