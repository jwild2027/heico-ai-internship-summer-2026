import importlib.util
from pathlib import Path


def test_v27_scripts_importable():
    for script in (
        "scripts/build/router/build_trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.py",
        "scripts/maintenance/serving/check_trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27_quality.py",
        "scripts/operations/serving/serve_trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
