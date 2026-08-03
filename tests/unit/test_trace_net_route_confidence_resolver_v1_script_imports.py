import importlib.util
from pathlib import Path


def test_scripts_importable():
    for rel in [
        "scripts/build/router/build_trace_net_route_confidence_resolver_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_route_confidence_resolver_v1_quality.py",
    ]:
        path = Path(rel)
        assert path.exists()
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
