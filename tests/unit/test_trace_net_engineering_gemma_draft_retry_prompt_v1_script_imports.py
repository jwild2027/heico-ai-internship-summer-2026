
import subprocess
import sys
from pathlib import Path


def test_scripts_help_execute_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    scripts = [
        "scripts/build/writing/build_trace_net_engineering_gemma_draft_retry_prompt_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_engineering_gemma_draft_retry_prompt_v1_quality.py",
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
    build_help = subprocess.run(
        [sys.executable, "scripts/build/writing/build_trace_net_engineering_gemma_draft_retry_prompt_v1.py", "--help"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert "--prompt-style" in build_help.stdout
    assert "--target-sentences" in build_help.stdout
