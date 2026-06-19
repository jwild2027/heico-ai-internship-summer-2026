import importlib.util
from pathlib import Path


def test_scripts_are_importable():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build_trace_net_table_crop_margin_expansion_experiment_v1.py",
        "scripts/check_trace_net_table_crop_margin_expansion_experiment_v1_quality.py",
    ]:
        path = root / rel
        assert path.exists()
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
