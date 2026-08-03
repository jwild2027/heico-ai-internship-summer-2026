import subprocess
import sys


def test_part_family_build_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/build/ingestion/build_trace_net_part_family_fast_answer_composer_v1.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "part-family" in result.stdout
