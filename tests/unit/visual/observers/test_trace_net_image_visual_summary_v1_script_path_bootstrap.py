from __future__ import annotations

from pathlib import Path


def test_build_script_bootstraps_repo_root_before_tiff_import() -> None:
    text = Path("scripts/build/visual/build_trace_net_image_visual_summary_v1.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in text
    assert "sys.path.insert(0, str(_REPO_ROOT))" in text
    assert text.index("sys.path.insert") < text.index("from tiff.trace_net_image_visual_summary_v1 import main_build")


def test_quality_script_bootstraps_repo_root_before_tiff_import() -> None:
    text = Path("scripts/maintenance/visual/check_trace_net_image_visual_summary_v1_quality.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in text
    assert "sys.path.insert(0, str(_REPO_ROOT))" in text
    assert text.index("sys.path.insert") < text.index("from tiff.trace_net_image_visual_summary_v1 import main_check")
