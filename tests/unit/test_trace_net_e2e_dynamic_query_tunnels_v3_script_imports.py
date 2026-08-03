import importlib.util
from pathlib import Path


def test_scripts_import_without_side_effects():
    for rel in [
        "scripts/build/retrieval/build_trace_net_e2e_dynamic_query_tunnels_v3.py",
        "scripts/maintenance/benchmark/check_trace_net_e2e_dynamic_query_tunnels_v3_quality.py",
    ]:
        path = Path(rel)
        assert path.exists(), rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "main")
