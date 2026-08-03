import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs_directly():
    proc = subprocess.run(
        [sys.executable, "scripts/build/graph/build_trace_net_leiden_community_quality_audit_v1.py", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    assert "Leiden Community Quality Audit" in proc.stdout


def test_check_script_help_runs_directly():
    proc = subprocess.run(
        [sys.executable, "scripts/maintenance/graph/check_trace_net_leiden_community_quality_audit_v1_quality.py", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    assert "Leiden Community Quality Audit" in proc.stdout
