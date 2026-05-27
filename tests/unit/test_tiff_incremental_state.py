from __future__ import annotations

from pathlib import Path
import time

from tiff.incremental_state import build_changed_tiff_list, read_changed_list


def test_incremental_state_first_run_marks_all_tiffs_changed(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    (root / "a.tif").write_bytes(b"one")
    (root / "b.TIFF").write_bytes(b"two")
    (root / "ignore.txt").write_text("nope", encoding="utf-8")

    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    result = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)

    assert result.summary.files_seen == 2
    assert result.summary.new_files == 2
    assert result.summary.changed_files == 0
    assert result.summary.unchanged_files == 0
    assert result.summary.changed_list_count == 2
    assert len(read_changed_list(changed_list)) == 2


def test_incremental_state_second_run_marks_unchanged(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    (root / "a.tif").write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)
    result = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)

    assert result.summary.files_seen == 1
    assert result.summary.new_files == 0
    assert result.summary.changed_files == 0
    assert result.summary.unchanged_files == 1
    assert result.summary.changed_list_count == 0
    assert read_changed_list(changed_list) == ()


def test_incremental_state_detects_changed_file(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    file_path = root / "a.tif"
    file_path.write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)
    time.sleep(0.001)
    file_path.write_bytes(b"two")

    result = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)

    assert result.summary.changed_files == 1
    assert result.summary.changed_list_count == 1
    assert read_changed_list(changed_list) == (str(file_path),)


def test_incremental_state_marks_missing_files(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    file_path = root / "a.tif"
    file_path.write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)
    file_path.unlink()
    result = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)

    assert result.summary.files_seen == 0
    assert result.summary.missing_files == 1
    assert result.summary.changed_list_count == 0


def test_incremental_state_preview_does_not_write_state_or_changed_list(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    (root / "a.tif").write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    preview = build_changed_tiff_list(
        root=root,
        state_db_path=state_db,
        changed_list_path=changed_list,
        persist=False,
    )

    assert preview.summary.new_files == 1
    assert preview.summary.changed_list_count == 1
    assert not state_db.exists()
    assert not changed_list.exists()

    committed = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)

    assert committed.summary.new_files == 1
    assert committed.summary.changed_list_count == 1
    assert state_db.exists()
    assert len(read_changed_list(changed_list)) == 1


def test_incremental_state_preview_after_commit_does_not_change_next_run(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    file_path = root / "a.tif"
    file_path.write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)
    time.sleep(0.001)
    file_path.write_bytes(b"two")

    preview = build_changed_tiff_list(
        root=root,
        state_db_path=state_db,
        changed_list_path=changed_list,
        persist=False,
    )
    committed = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)

    assert preview.summary.changed_files == 1
    assert committed.summary.changed_files == 1
    assert read_changed_list(changed_list) == (str(file_path),)


def test_incremental_state_dry_run_can_write_changed_list_without_committing_state(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    file_path = root / "a.tif"
    file_path.write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    preview = build_changed_tiff_list(
        root=root,
        state_db_path=state_db,
        changed_list_path=changed_list,
        commit_state=False,
        write_list=True,
    )

    assert preview.summary.new_files == 1
    assert read_changed_list(changed_list) == (str(file_path),)
    assert not state_db.exists()

    committed = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed_list)

    assert committed.summary.new_files == 1
    assert committed.summary.changed_list_count == 1
