import importlib.util
from pathlib import Path


def test_v25_scripts_importable():
    for script in (
        "scripts/build_trace_net_e2e_live_orchestrator_endpoint_v25.py",
        "scripts/check_trace_net_e2e_live_orchestrator_endpoint_v25_quality.py",
        "scripts/serve_trace_net_e2e_live_orchestrator_endpoint_v25.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
