from __future__ import annotations

import json
from pathlib import Path

from tiff.incremental_readiness import (
    audit_incremental_readiness,
    format_incremental_readiness_report,
    preview_incremental_changes,
)
from tiff.incremental_state import IncrementalStateDB


def _write_config(path: Path, root: Path, state_db: Path, db_path: Path, export_dir: Path, questions: Path) -> None:
    path.write_text(
        "\n".join(
            [
                f"tiff_root: {root.as_posix()}",
                f"incremental_state_db: {state_db.as_posix()}",
                f"changed_tiffs: {(path.parent / 'changed_tiffs.txt').as_posix()}",
                "hash_mode: stat",
                f"db_path: {db_path.as_posix()}",
                f"rescarta_export_dir: {export_dir.as_posix()}",
                f"eval_questions: {questions.as_posix()}",
                "backend_mode: changed-pages",
            ]
        ),
        encoding="utf-8",
    )


def test_preview_does_not_create_missing_state_db(tmp_path: Path) -> None:
    root = tmp_path / "tiffs"
    root.mkdir()
    (root / "one.tif").write_bytes(b"fake")
    state_db = tmp_path / "missing_state.db"

    preview = preview_incremental_changes(tiff_root=root, state_db=state_db, hash_mode="stat")

    assert preview.files_seen == 1
    assert preview.new_files == 1
    assert preview.changed_list_count == 1
    assert preview.state_db_exists is False
    assert not state_db.exists()


def test_preview_uses_existing_committed_state(tmp_path: Path) -> None:
    root = tmp_path / "tiffs"
    root.mkdir()
    tif = root / "one.tif"
    tif.write_bytes(b"fake")
    state_db = tmp_path / "state.db"

    state = IncrementalStateDB(state_db)
    first = state.detect_changes(root, hash_mode="stat")
    state.commit_summary(first)

    preview = preview_incremental_changes(tiff_root=root, state_db=state_db, hash_mode="stat")

    assert preview.files_seen == 1
    assert preview.state_rows == 1
    assert preview.unchanged_files == 1
    assert preview.changed_list_count == 0


def test_audit_reports_ok_when_required_files_exist(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "tiffs"
    export_dir = tmp_path / "rescarta_exports"
    db_path = tmp_path / "tiff_search.db"
    questions = tmp_path / "rag_eval_questions.json"
    state_db = tmp_path / "state.db"
    root.mkdir()
    export_dir.mkdir()
    (root / "one.tif").write_bytes(b"fake")
    db_path.write_bytes(b"sqlite placeholder")
    questions.write_text("[]", encoding="utf-8")

    # The audit checks for repo-relative changed-page files. Create them in a
    # temp cwd so the test does not depend on the checkout's current files.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tiff").mkdir()
    (tmp_path / "scripts" / "update_changed_page_backend.py").write_text("", encoding="utf-8")
    (tmp_path / "tiff" / "changed_page_update.py").write_text("", encoding="utf-8")

    config = tmp_path / "local_config.yaml"
    _write_config(config, root, state_db, db_path, export_dir, questions)

    report = audit_incremental_readiness(
        config_path=config,
        backend_mode="changed-pages",
        require_clean_quality=False,
        quality_path=tmp_path / "missing_quality.json",
        manifest_path=tmp_path / "missing_manifest.json",
    )

    assert report.ok is True
    assert report.changed_pages_backend_available is True
    assert report.changed_pages_command_planned is True
    assert report.dry_run_state_commit_safe is True
    assert report.failed_downstream_state_commit_safe is True
    assert report.successful_downstream_state_commit_allowed is True
    assert report.preview_changed_list_count == 1


def test_audit_can_require_clean_quality(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "tiffs"
    export_dir = tmp_path / "rescarta_exports"
    db_path = tmp_path / "tiff_search.db"
    questions = tmp_path / "rag_eval_questions.json"
    state_db = tmp_path / "state.db"
    root.mkdir()
    export_dir.mkdir()
    (root / "one.tif").write_bytes(b"fake")
    db_path.write_bytes(b"sqlite placeholder")
    questions.write_text("[]", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tiff").mkdir()
    (tmp_path / "scripts" / "update_changed_page_backend.py").write_text("", encoding="utf-8")
    (tmp_path / "tiff" / "changed_page_update.py").write_text("", encoding="utf-8")
    quality = tmp_path / "quality.json"
    manifest = tmp_path / "manifest.json"
    quality.write_text(json.dumps({"status": "OK"}), encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "status": "ok",
                "run_id": "TEST",
                "steps": [{"name": "source_link_audit", "status": "OK"}],
                "source_link_summary": {
                    "local_source_review_ready": True,
                    "real_rescarta_deep_link_ready": False,
                },
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "local_config.yaml"
    _write_config(config, root, state_db, db_path, export_dir, questions)

    report = audit_incremental_readiness(
        config_path=config,
        require_clean_quality=True,
        quality_path=quality,
        manifest_path=manifest,
    )

    assert report.ok is True
    assert report.quality_status == "OK"
    assert report.manifest_status == "ok"
    assert report.manifest_has_source_link_audit is True
    assert report.source_local_review_ready is True
    assert report.source_real_rescarta_ready is False


def test_audit_accepts_lowercase_quality_status_and_current_source_keys(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "tiffs"
    export_dir = tmp_path / "rescarta_exports"
    db_path = tmp_path / "tiff_search.db"
    questions = tmp_path / "rag_eval_questions.json"
    state_db = tmp_path / "state.db"
    root.mkdir()
    export_dir.mkdir()
    (root / "one.tif").write_bytes(b"fake")
    db_path.write_bytes(b"sqlite placeholder")
    questions.write_text("[]", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tiff").mkdir()
    (tmp_path / "scripts" / "update_changed_page_backend.py").write_text("", encoding="utf-8")
    (tmp_path / "tiff" / "changed_page_update.py").write_text("", encoding="utf-8")

    quality = tmp_path / "quality.json"
    manifest = tmp_path / "manifest.json"
    quality.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "status": "ok",
                "run_id": "TEST",
                "steps": [{"name": "source_link_audit", "status": "OK"}],
                "source_link_summary": {
                    "ready_for_local_source_review": True,
                    "ready_for_real_rescarta_deeplinks": False,
                },
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "local_config.yaml"
    _write_config(config, root, state_db, db_path, export_dir, questions)

    report = audit_incremental_readiness(
        config_path=config,
        require_clean_quality=True,
        quality_path=quality,
        manifest_path=manifest,
    )

    assert report.ok is True
    assert report.quality_status == "ok"
    assert report.manifest_status == "ok"
    assert report.manifest_has_source_link_audit is True
    assert report.source_local_review_ready is True
    assert report.source_real_rescarta_ready is False
    assert not report.errors


def test_format_report_is_command_line_first(tmp_path: Path) -> None:
    root = tmp_path / "tiffs"
    root.mkdir()
    (root / "one.tif").write_bytes(b"fake")
    report = audit_incremental_readiness(
        config_path=tmp_path / "missing_config.yaml",
        require_clean_quality=False,
    )

    text = format_incremental_readiness_report(report)

    assert "Incremental pipeline readiness audit" in text
    assert "Path/config checks:" in text
    assert "Safe-commit checks:" in text
    assert "Read-only change preview:" in text
