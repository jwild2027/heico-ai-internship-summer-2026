from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.list_changed_tiffs_for_scan import changed_tiff_rows, ensure_schema, main


def make_inventory_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE source_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            rel_path TEXT NOT NULL,
            file_sha256 TEXT,
            status TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE tiff_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_id INTEGER NOT NULL,
            page_index INTEGER NOT NULL,
            change_status TEXT NOT NULL
        );
        """
    )
    files = [
        (1, "/abs/a.tif", "a.tif", "hash-a", "active"),
        (2, "/abs/b.tif", "b.tif", "hash-b", "active"),
        (3, "/abs/c.tif", "c.tif", "hash-c", "active"),
        (4, "/abs/deleted.tif", "deleted.tif", "hash-d", "missing"),
    ]
    conn.executemany(
        "INSERT INTO source_files(id, path, rel_path, file_sha256, status) VALUES (?, ?, ?, ?, ?)",
        files,
    )
    pages = [
        (1, 1, "unchanged"),
        (1, 2, "changed"),
        (2, 1, "new"),
        (3, 1, "unchanged"),
        (4, 1, "changed"),
    ]
    conn.executemany(
        "INSERT INTO tiff_pages(source_file_id, page_index, change_status) VALUES (?, ?, ?)",
        pages,
    )
    conn.commit()
    conn.close()


def test_changed_tiff_rows_returns_active_files_with_new_or_changed_pages(tmp_path: Path) -> None:
    db = tmp_path / "inventory.db"
    make_inventory_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    rows = changed_tiff_rows(conn)
    assert [row["rel_path"] for row in rows] == ["a.tif", "b.tif"]
    assert rows[0]["matching_pages"] == 1
    assert rows[0]["page_statuses"] == "2:changed"


def test_cli_writes_text_list(tmp_path: Path) -> None:
    db = tmp_path / "inventory.db"
    out = tmp_path / "changed.txt"
    make_inventory_db(db)
    code = main(["--inventory-db", str(db), "--output", str(out), "--relative"])
    assert code == 0
    assert out.read_text(encoding="utf-8").splitlines() == ["a.tif", "b.tif"]


def test_cli_writes_empty_file_when_no_matching_statuses(tmp_path: Path) -> None:
    db = tmp_path / "inventory.db"
    out = tmp_path / "changed.txt"
    make_inventory_db(db)
    code = main(["--inventory-db", str(db), "--output", str(out), "--statuses", "changed_only"])
    assert code == 0
    assert out.read_text(encoding="utf-8") == ""
