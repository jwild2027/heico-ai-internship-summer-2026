from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "tiff_inventory_hash_crawler.py"


def load_crawler():
    spec = importlib.util.spec_from_file_location("tiff_inventory_hash_crawler", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_tiff(path: Path, value: int = 255, size: tuple[int, int] = (20, 10)) -> None:
    img = Image.new("L", size, color=value)
    img.save(path, format="TIFF")


def test_inventory_first_run_marks_new(tmp_path: Path):
    crawler = load_crawler()
    root = tmp_path / "tiffs"
    root.mkdir()
    make_tiff(root / "a.tif", value=255)
    db = tmp_path / "inventory.db"

    rc = crawler.main(["--root", str(root), "--db", str(db)])
    assert rc == 0

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM source_files").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM tiff_pages").fetchone()[0] == 1
    assert conn.execute("SELECT change_status FROM tiff_pages").fetchone()[0] == "new"
    conn.close()


def test_inventory_second_run_marks_unchanged(tmp_path: Path):
    crawler = load_crawler()
    root = tmp_path / "tiffs"
    root.mkdir()
    make_tiff(root / "a.tif", value=200)
    db = tmp_path / "inventory.db"

    assert crawler.main(["--root", str(root), "--db", str(db)]) == 0
    assert crawler.main(["--root", str(root), "--db", str(db)]) == 0

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT change_status FROM tiff_pages").fetchone()[0] == "unchanged"
    assert conn.execute("SELECT COUNT(*) FROM crawl_runs").fetchone()[0] == 2
    conn.close()


def test_inventory_detects_changed_page(tmp_path: Path):
    crawler = load_crawler()
    root = tmp_path / "tiffs"
    root.mkdir()
    tiff_path = root / "a.tif"
    make_tiff(tiff_path, value=50)
    db = tmp_path / "inventory.db"

    assert crawler.main(["--root", str(root), "--db", str(db)]) == 0
    make_tiff(tiff_path, value=100)
    assert crawler.main(["--root", str(root), "--db", str(db)]) == 0

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT change_status FROM tiff_pages").fetchone()[0] == "changed"
    conn.close()


def test_inventory_mark_missing(tmp_path: Path):
    crawler = load_crawler()
    root = tmp_path / "tiffs"
    root.mkdir()
    a = root / "a.tif"
    b = root / "b.tif"
    make_tiff(a, value=10)
    make_tiff(b, value=20)
    db = tmp_path / "inventory.db"

    assert crawler.main(["--root", str(root), "--db", str(db)]) == 0
    b.unlink()
    assert crawler.main(["--root", str(root), "--db", str(db), "--mark-missing"]) == 0

    conn = sqlite3.connect(db)
    rows = dict(conn.execute("SELECT rel_path, status FROM source_files").fetchall())
    assert rows["a.tif"] == "active"
    assert rows["b.tif"] == "missing"
    conn.close()
