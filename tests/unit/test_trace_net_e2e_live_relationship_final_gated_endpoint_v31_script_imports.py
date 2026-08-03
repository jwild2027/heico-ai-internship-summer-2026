import importlib.util
from pathlib import Path


def test_v31_scripts_importable():
    for script in (
        "scripts/benchmark/graph/build_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py",
        "scripts/benchmark/serving/check_trace_net_e2e_live_relationship_final_gated_endpoint_v31_quality.py",
        "scripts/benchmark/serving/serve_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
