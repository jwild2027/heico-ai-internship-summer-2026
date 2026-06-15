import subprocess
import sys


def test_module_imports():
    import tiff.trace_net_leiden_navigation_metadata_bridge_v1 as module

    assert module.SCHEMA_VERSION == "trace_net_leiden_navigation_metadata_bridge_v1"


def test_build_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/build_trace_net_leiden_navigation_metadata_bridge_v1.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "leiden-representative-label-tightening" in result.stdout


def test_quality_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/check_trace_net_leiden_navigation_metadata_bridge_v1_quality.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "report-path" in result.stdout
