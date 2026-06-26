
import subprocess
import sys
from pathlib import Path


def test_scripts_help_execute_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    scripts = [
        "scripts/build_trace_net_engineering_draft_final_gate_v1.py",
        "scripts/check_trace_net_engineering_draft_final_gate_v1_quality.py",
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
    check_help = subprocess.run(
        [sys.executable, "scripts/check_trace_net_engineering_draft_final_gate_v1_quality.py", "--help"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert "--max-blocked-risky-phrase-hits" in check_help.stdout
    assert "--min-negated-risky-phrase-hits" in check_help.stdout
