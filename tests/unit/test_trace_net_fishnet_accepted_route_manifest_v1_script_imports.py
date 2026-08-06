
import subprocess
import sys
from pathlib import Path


def test_scripts_help_execute_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    scripts = [
        "scripts/build/ocr/build_trace_net_fishnet_accepted_route_manifest_v1.py",
        "scripts/maintenance/s2_ocr/check_trace_net_fishnet_accepted_route_manifest_v1_quality.py",
    ]
    for script in scripts:
        completed = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert completed.returncode == 0, completed.stderr
