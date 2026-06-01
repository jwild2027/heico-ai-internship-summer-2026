from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_graph_org_chart_script_help_runs_directly() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "build_graph_org_chart_site.py"
    if not script.exists():
        return

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(repo_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--expect-pages" in result.stdout
    assert "--expect-documents" in result.stdout
