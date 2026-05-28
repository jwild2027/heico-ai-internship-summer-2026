from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_audit_document_organization_accepts_no_refresh_manifest(monkeypatch) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "audit_document_organization.py"
    spec = importlib.util.spec_from_file_location("audit_document_organization_cli", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_document_organization_cli"] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(sys, "argv", ["audit_document_organization.py", "--no-refresh-manifest"])
    args = module.parse_args()
    assert args.no_refresh_manifest is True
