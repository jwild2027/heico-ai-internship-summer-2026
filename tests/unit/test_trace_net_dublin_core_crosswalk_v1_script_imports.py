import importlib.util
from pathlib import Path


def test_scripts_importable() -> None:
    for rel in [
        "scripts/build/core/build_trace_net_dublin_core_crosswalk_v1.py",
        "scripts/maintenance/core/check_trace_net_dublin_core_crosswalk_v1_quality.py",
    ]:
        path = Path(rel)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "main")
