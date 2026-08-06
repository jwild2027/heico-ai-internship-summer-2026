import importlib.util
from pathlib import Path


def test_scripts_importable():
    for rel in [
        "scripts/build/serving/build_trace_net_ask_api_final_return_policy_v21.py",
        "scripts/operations/serving/run_trace_net_ask_api_final_return_policy_v21.py",
        "scripts/maintenance/serving/check_trace_net_ask_api_final_return_policy_v21_quality.py",
    ]:
        path = Path(rel)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
