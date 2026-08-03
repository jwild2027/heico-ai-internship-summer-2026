import importlib.util
from pathlib import Path


def test_scripts_are_importable() -> None:
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build/core/build_trace_net_dublin_core_crosswalk_refinement_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_dublin_core_crosswalk_refinement_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
