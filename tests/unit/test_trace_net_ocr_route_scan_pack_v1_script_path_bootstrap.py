from pathlib import Path


def test_scripts_bootstrap_repo_root():
    text = Path("scripts/build_trace_net_ocr_route_scan_pack_v1.py").read_text(encoding="utf-8")
    assert "sys.path.insert" in text
    assert "parents[1]" in text
