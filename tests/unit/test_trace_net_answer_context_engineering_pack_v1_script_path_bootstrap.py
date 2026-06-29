import runpy
from pathlib import Path


def test_scripts_have_path_bootstrap():
    root = Path(__file__).resolve().parents[2]
    build = root / "scripts" / "build_trace_net_answer_context_engineering_pack_v1.py"
    check = root / "scripts" / "check_trace_net_answer_context_engineering_pack_v1_quality.py"
    assert "sys.path.insert" in build.read_text(encoding="utf-8")
    assert "sys.path.insert" in check.read_text(encoding="utf-8")
