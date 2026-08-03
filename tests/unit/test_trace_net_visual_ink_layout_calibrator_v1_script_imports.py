import subprocess
import sys


def test_build_script_help_imports():
    result = subprocess.run(
        [sys.executable, "scripts/build/visual/build_trace_net_visual_ink_layout_calibrator_v1.py", "--help"],
        cwd=".",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "visual ink/layout" in result.stdout.lower()


def test_quality_script_help_imports():
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/benchmark/check_trace_net_visual_ink_layout_calibrator_v1_quality.py", "--help"],
        cwd=".",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "quality" in result.stdout.lower()
