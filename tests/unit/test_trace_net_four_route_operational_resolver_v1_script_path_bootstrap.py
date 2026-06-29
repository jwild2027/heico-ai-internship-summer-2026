import subprocess
import sys


def test_scripts_help_bootstrap_from_repo_root():
    for script in [
        "scripts/build_trace_net_four_route_operational_resolver_v1.py",
        "scripts/check_trace_net_four_route_operational_resolver_v1_quality.py",
    ]:
        proc = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0
        assert "TRACE-Net" in proc.stdout
