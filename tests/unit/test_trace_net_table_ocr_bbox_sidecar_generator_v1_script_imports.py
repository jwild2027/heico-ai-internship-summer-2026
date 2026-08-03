import importlib.util
from pathlib import Path


def test_script_wrappers_importable():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build/tables/build_trace_net_table_ocr_bbox_sidecar_generator_v1.py",
        "scripts/maintenance/tables/check_trace_net_table_ocr_bbox_sidecar_generator_v1_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
