from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_script_help_invocations() -> None:
    root = Path(__file__).resolve().parents[2]
    for script in [
        "scripts/build_trace_net_human_review_queue_table_geometry_integration_v1.py",
        "scripts/check_trace_net_human_review_queue_table_geometry_integration_v1_quality.py",
    ]:
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()
