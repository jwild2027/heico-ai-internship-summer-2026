import subprocess
import sys


def test_build_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/benchmark/build_trace_net_retrieval_payload_audit_v1.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--loader-contract-audit" in result.stdout


def test_check_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/benchmark/check_trace_net_retrieval_payload_audit_v1_quality.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--report-path" in result.stdout
