import py_compile
import subprocess
import sys
from pathlib import Path


def test_evidence_packager_scripts_compile():
    py_compile.compile("scripts/build_trace_net_table_route_evidence_packager_v1.py", doraise=True)
    py_compile.compile("scripts/check_trace_net_table_route_evidence_packager_v1_quality.py", doraise=True)


def test_evidence_packager_scripts_help_from_repo_root():
    repo_root = Path(__file__).resolve().parents[2]
    for script in [
        "scripts/build_trace_net_table_route_evidence_packager_v1.py",
        "scripts/check_trace_net_table_route_evidence_packager_v1_quality.py",
    ]:
        completed = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=repo_root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert completed.returncode == 0, completed.stderr
        assert "table-route evidence" in (completed.stdout + completed.stderr).lower()
