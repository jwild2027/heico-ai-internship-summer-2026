import importlib.util
from pathlib import Path


def test_scripts_import_without_running():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build_trace_net_table_crop_selection_diagnostics_v1.py",
        "scripts/check_trace_net_table_crop_selection_diagnostics_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
