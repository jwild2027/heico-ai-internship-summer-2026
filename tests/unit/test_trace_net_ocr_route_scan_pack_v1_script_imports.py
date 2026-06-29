import importlib.util
from pathlib import Path


def test_scripts_import():
    for script in [
        "scripts/build_trace_net_ocr_route_scan_pack_v1.py",
        "scripts/check_trace_net_ocr_route_scan_pack_v1_quality.py",
    ]:
        path = Path(script)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
