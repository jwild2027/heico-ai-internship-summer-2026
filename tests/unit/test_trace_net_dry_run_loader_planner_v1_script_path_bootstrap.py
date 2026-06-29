from __future__ import annotations

from pathlib import Path


def test_scripts_bootstrap_repo_root() -> None:
    for path in [
        Path("scripts/build_trace_net_dry_run_loader_planner_v1.py"),
        Path("scripts/check_trace_net_dry_run_loader_planner_v1_quality.py"),
    ]:
        text = path.read_text(encoding="utf-8")
        assert "ROOT = Path(__file__).resolve().parents[1]" in text
        assert "sys.path.insert(0, str(ROOT))" in text
