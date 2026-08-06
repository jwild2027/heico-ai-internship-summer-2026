import importlib.util
from pathlib import Path


def test_build_and_check_scripts_import():
    for rel in [
        "scripts/build/core/build_trace_net_loader_contract_audit_v1.py",
        "scripts/maintenance/core/check_trace_net_loader_contract_audit_v1_quality.py",
    ]:
        path = Path(rel)
        assert path.exists()
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
