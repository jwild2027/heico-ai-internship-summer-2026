import subprocess
import sys


def test_scripts_help_bootstrap_from_repo_root():
    for script in [
        "scripts/build/validation/build_trace_net_route_validator_runner_v1.py",
        "scripts/maintenance/s6_retrieval/check_trace_net_route_validator_runner_v1_quality.py",
    ]:
        proc = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0
        assert "TRACE-Net" in proc.stdout
