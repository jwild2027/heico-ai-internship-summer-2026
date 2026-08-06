from __future__ import annotations

import os
import time
from pathlib import Path

from tiff.incremental_state import IncrementalStateDB, write_changed_list, read_changed_list


def make_tiff(path: Path, text: bytes = b"fake tiff data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text)


def test_detect_changes_does_not_commit_until_explicit(tmp_path: Path):
    root = tmp_path / "root"
    make_tiff(root / "a.tif")
    db = IncrementalStateDB(tmp_path / "state.db")

    first = db.detect_changes(root)
    assert first.new_files == 1
    assert first.changed_list_count == 1

    # A second detect still sees the file as new because no commit happened.
    second = db.detect_changes(root)
    assert second.new_files == 1
    assert second.changed_list_count == 1

    db.commit_summary(first)
    third = db.detect_changes(root)
    assert third.new_files == 0
    assert third.changed_files == 0
    assert third.unchanged_files == 1
    assert third.changed_list_count == 0


def test_changed_file_is_not_consumed_until_commit(tmp_path: Path):
    root = tmp_path / "root"
    target = root / "a.tif"
    make_tiff(target, b"v1")
    db = IncrementalStateDB(tmp_path / "state.db")
    db.commit_summary(db.detect_changes(root))

    # Change content and mtime so stat mode detects the change reliably.
    time.sleep(0.002)
    target.write_bytes(b"v2 longer")

    changed = db.detect_changes(root)
    assert changed.changed_files == 1
    assert changed.changed_list_count == 1

    still_changed = db.detect_changes(root)
    assert still_changed.changed_files == 1
    assert still_changed.changed_list_count == 1

    db.commit_summary(changed)
    clean = db.detect_changes(root)
    assert clean.unchanged_files == 1
    assert clean.changed_list_count == 0


def test_write_and_read_changed_list(tmp_path: Path):
    out = tmp_path / "changed.txt"
    write_changed_list(["a.tif", "b.tif"], out)
    assert read_changed_list(out) == ["a.tif", "b.tif"]
