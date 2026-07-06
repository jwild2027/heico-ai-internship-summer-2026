from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_canonical_runtime_map_v1 import (
    build_runtime_map,
    check_runtime_map,
    scan_backup_candidates,
)


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_runtime_map_marks_primary_and_support_modules(tmp_path: Path) -> None:
    required_paths = [
        "tiff/trace_net_openwebui_page_context_bridge_v1.py",
        "tiff/trace_net_page_context_pack_v3.py",
        "scripts/serve_trace_net_openwebui_page_context_bridge_v1.py",
        "tiff/trace_net_webui_self_rag_crag_bridge_v1.py",
        "tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py",
        "tiff/trace_net_engineering_engram_core_v1.py",
        "tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py",
        "tiff/trace_net_engineering_engram_self_rag_critic_v1.py",
        "tiff/trace_net_engineering_engram_crag_repair_v1.py",
        "tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py",
    ]
    for rel in required_paths:
        _touch(tmp_path / rel, "# placeholder\n")

    manifest = build_runtime_map(repo_root=tmp_path, output_dir=tmp_path / "out")

    assert manifest["quality_status"] == "PASS"
    assert manifest["selected_openwebui_answer_path"]["implementation_module"] == (
        "tiff/trace_net_openwebui_page_context_bridge_v1.py"
    )
    assert manifest["summary"]["active_support_existing_count"] >= 5
    assert manifest["summary"]["cleanup_allowed_now"] is False


def test_backup_candidates_are_never_cleanup_allowed_now(tmp_path: Path) -> None:
    _touch(tmp_path / "tiff/trace_net_example.py.pre_fix.bak", "# backup\n")
    _touch(tmp_path / "scripts/example.py.bak", "# backup\n")

    backups = scan_backup_candidates(tmp_path)

    assert len(backups) == 2
    assert all(item["status"] == "backup_snapshot" for item in backups)
    assert all(item["cleanup_allowed_now"] is False for item in backups)


def test_quality_check_fails_missing_primary_path(tmp_path: Path) -> None:
    _touch(tmp_path / "tiff/trace_net_page_context_pack_v3.py", "# only page context\n")
    manifest = build_runtime_map(repo_root=tmp_path, output_dir=tmp_path / "out")

    quality = check_runtime_map(
        tmp_path / "out" / "trace_net_canonical_runtime_map_v1.json",
        output_path=tmp_path / "out" / "quality.json",
        min_active_support=5,
        require_primary_openwebui_path=True,
        require_no_cleanup_allowed=True,
    )

    assert manifest["quality_status"] == "REVIEW"
    assert quality["quality_status"] == "FAIL"
    assert "primary_openwebui_module_missing" in quality["failure_reasons"]
