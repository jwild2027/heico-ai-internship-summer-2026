from pathlib import Path

from tiff.incremental_state import build_changed_tiff_list, read_changed_list


def test_preview_mode_removes_empty_sqlite_state_db(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    (root / "a.tif").write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    result = build_changed_tiff_list(
        root=root,
        state_db_path=state_db,
        changed_list_path=changed_list,
        persist=False,
    )

    assert result.summary.new_files == 1
    assert result.summary.changed_list_count == 1
    assert not state_db.exists()
    assert not changed_list.exists()


def test_dry_run_can_write_list_without_leaving_state_db(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    file_path = root / "a.tif"
    file_path.write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"

    result = build_changed_tiff_list(
        root=root,
        state_db_path=state_db,
        changed_list_path=changed_list,
        commit_state=False,
        write_list=True,
    )

    assert result.summary.new_files == 1
    assert read_changed_list(changed_list) == (str(file_path.resolve()),)
    assert not state_db.exists()
