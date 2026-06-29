import subprocess
import sys


def test_build_script_help_runs_from_scripts_path():
    result = subprocess.run(
        [sys.executable, "scripts/build_trace_net_route_label_taxonomy_v1.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Build TRACE-Net route label taxonomy" in result.stdout
