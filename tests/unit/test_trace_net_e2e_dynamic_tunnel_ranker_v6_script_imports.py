import importlib.util
from pathlib import Path


def test_scripts_importable():
    for rel in [
        "scripts/build_trace_net_e2e_dynamic_tunnel_ranker_v6.py",
        "scripts/check_trace_net_e2e_dynamic_tunnel_ranker_v6_quality.py",
    ]:
        path = Path(rel)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
