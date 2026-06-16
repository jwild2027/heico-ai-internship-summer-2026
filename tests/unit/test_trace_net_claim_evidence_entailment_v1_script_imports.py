import subprocess
import sys


def test_build_script_help_runs_directly():
    result = subprocess.run(
        [sys.executable, "scripts/build_trace_net_claim_evidence_entailment_v1.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "dynamic-final-gate" in result.stdout


def test_quality_script_help_runs_directly():
    result = subprocess.run(
        [sys.executable, "scripts/check_trace_net_claim_evidence_entailment_v1_quality.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "report-path" in result.stdout
