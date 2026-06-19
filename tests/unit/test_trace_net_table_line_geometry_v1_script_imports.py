from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_script_imports() -> None:
    import scripts.build_trace_net_table_line_geometry_v1 as build_script
    import scripts.check_trace_net_table_line_geometry_v1_quality as check_script

    assert build_script.main is not None
    assert check_script.main is not None


def test_scripts_help_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for script in (
        "scripts/build_trace_net_table_line_geometry_v1.py",
        "scripts/check_trace_net_table_line_geometry_v1_quality.py",
    ):
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()
