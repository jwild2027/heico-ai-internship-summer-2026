import importlib.util
import subprocess
import sys
from pathlib import Path


def test_run_script_imports():
    path = Path("scripts/run_trace_net_table_route_value_audit_lep_v4_preset_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("run_lep_v4_preset", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_check_script_imports():
    path = Path("scripts/check_trace_net_table_route_value_audit_lep_v4_preset_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_lep_v4_preset", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_run_script_direct_cli_help_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/run_trace_net_table_route_value_audit_lep_v4_preset_v1.py", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--table-route-value-normalizer" in completed.stdout


def test_check_script_direct_cli_help_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/check_trace_net_table_route_value_audit_lep_v4_preset_v1_quality.py", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--min-source-normalized-records" in completed.stdout
