import subprocess
import sys


def test_scripts_have_help_from_repo_root():
    for script in [
        "scripts/build/core/build_trace_net_loader_contract_audit_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_loader_contract_audit_v1_quality.py",
    ]:
        proc = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True)
        assert proc.returncode == 0
        assert "trace-net" in proc.stdout.lower() or "TRACE-Net" in proc.stdout
