import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build/tables/build_trace_net_table_margin_detector_parity_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("build_margin_detector_parity", path)
    assert spec and spec.loader


def test_quality_script_imports():
    path = Path("scripts/maintenance/s2_ocr/check_trace_net_table_margin_detector_parity_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_margin_detector_parity", path)
    assert spec and spec.loader
