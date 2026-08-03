import importlib.util
from pathlib import Path


def test_scripts_importable():
    for script in [
        "scripts/build/serving/build_trace_net_e2e_dynamic_query_endpoint_v1.py",
        "scripts/maintenance/serving/check_trace_net_e2e_dynamic_query_endpoint_v1_quality.py",
        "scripts/operations/serving/serve_trace_net_e2e_dynamic_query_endpoint_v1.py",
    ]:
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
