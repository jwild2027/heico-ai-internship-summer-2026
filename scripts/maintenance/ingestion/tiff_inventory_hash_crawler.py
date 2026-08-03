#!/usr/bin/env python3
"""Stage 0 TIFF inventory/hash crawler.

This crawler is intentionally separate from the OCR/classification scanner.
Use it to inventory large TIFF folders, compute stable file/page hashes,
detect new/changed/unchanged pages, and report duplicate page content.

Recommended first run:
    python scripts/maintenance/ingestion/tiff_inventory_hash_crawler.py --root local_data/sample_tiffs --db local_data/db/tiff_inventory_hashes.db --limit-files 10

Recommended second run:
    python scripts/maintenance/ingestion/tiff_inventory_hash_crawler.py --root local_data/sample_tiffs --db local_data/db/tiff_inventory_hashes.db --limit-files 10

The first run should show new pages. The second run should show unchanged pages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

try:
    import pytesseract
except Exception:  # pytesseract is optional unless --ocr is used
    pytesseract = None

TIFF_SUFFIXES = {".tif", ".tiff"}
SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def quick_file_fingerprint(path: Path) -> str:
    """Cheap fallback fingerprint for quick crawls.

    This is not a cryptographic file identity. It is only useful for quick
    inventory passes where reading every byte would be too expensive.
    """
    stat = path.stat()
    payload = {
        "path_name": path.name,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    return "quick:" + canonical_json_hash(payload)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sha256_text(text: str) -> str:
    return sha256_bytes(normalize_text(text).encode("utf-8"))


def canonical_json_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(encoded.encode("utf-8"))


def normalized_page_image(frame: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(frame)
    return img.convert("L")


def pixel_sha256(frame: Image.Image) -> str:
    img = normalized_page_image(frame)
    h = hashlib.sha256()
    h.update(f"{img.mode}|{img.width}x{img.height}|".encode("ascii"))
    h.update(img.tobytes())
    return h.hexdigest()


def dhash64(frame: Image.Image, hash_size: int = 8) -> str:
    """Small perceptual-ish hash for near-duplicate grouping."""
    img = normalized_page_image(frame).resize((hash_size + 1, hash_size))
    pixels = list(img.getdata())
    bits = 0
    for y in range(hash_size):
        row = y * (hash_size + 1)
        for x in range(hash_size):
            bits = (bits << 1) | int(pixels[row + x] > pixels[row + x + 1])
    return f"{bits:016x}"


def hamming_hex(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def safe_rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def ocr_page(frame: Image.Image, lang: str, psm: int) -> tuple[str, Optional[float]]:
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed. Run without --ocr or install pytesseract.")
    img = normalized_page_image(frame)
    config = f"--psm {psm} -c preserve_interword_spaces=1"
    text = pytesseract.image_to_string(img, lang=lang, config=config) or ""
    confidence: Optional[float] = None
    try:
        data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)
        vals = []
        for raw in data.get("conf", []):
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if val >= 0:
                vals.append(val)
        if vals:
            confidence = sum(vals) / len(vals)
    except Exception:
        confidence = None
    return text, confidence


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS inventory_schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT OR REPLACE INTO inventory_schema_info(key, value)
        VALUES ('schema_version', '1');

        CREATE TABLE IF NOT EXISTS crawl_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            root TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            files_seen INTEGER NOT NULL DEFAULT 0,
            pages_seen INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            mode TEXT NOT NULL DEFAULT 'hash'
        );

        CREATE TABLE IF NOT EXISTS source_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            rel_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            file_sha256 TEXT NOT NULL,
            hash_mode TEXT NOT NULL DEFAULT 'sha256',
            frame_count INTEGER NOT NULL DEFAULT 0,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_run_id INTEGER,
            status TEXT NOT NULL DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS tiff_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
            page_index INTEGER NOT NULL,
            width_px INTEGER NOT NULL,
            height_px INTEGER NOT NULL,
            mode TEXT NOT NULL,
            file_sha256 TEXT NOT NULL,
            pixel_sha256 TEXT NOT NULL,
            dhash64 TEXT NOT NULL,
            ocr_sha256 TEXT,
            ocr_confidence REAL,
            ocr_text TEXT,
            page_content_sha256 TEXT NOT NULL,
            inventory_item_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            change_status TEXT NOT NULL,
            UNIQUE(source_file_id, page_index)
        );

        CREATE TABLE IF NOT EXISTS inventory_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES crawl_runs(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            rel_path TEXT,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_source_files_file_sha256 ON source_files(file_sha256);
        CREATE INDEX IF NOT EXISTS idx_source_files_status ON source_files(status);
        CREATE INDEX IF NOT EXISTS idx_source_files_last_run ON source_files(last_run_id);
        CREATE INDEX IF NOT EXISTS idx_tiff_pages_pixel_sha256 ON tiff_pages(pixel_sha256);
        CREATE INDEX IF NOT EXISTS idx_tiff_pages_ocr_sha256 ON tiff_pages(ocr_sha256);
        CREATE INDEX IF NOT EXISTS idx_tiff_pages_content_sha256 ON tiff_pages(page_content_sha256);
        CREATE INDEX IF NOT EXISTS idx_tiff_pages_dhash64 ON tiff_pages(dhash64);
        CREATE INDEX IF NOT EXISTS idx_tiff_pages_change_status ON tiff_pages(change_status);
        """
    )


def upsert_source_file(conn: sqlite3.Connection, root: Path, path: Path, file_hash: str, hash_mode: str, run_id: int) -> int:
    stat = path.stat()
    now = utc_now()
    rel_path = safe_rel_path(path, root)
    conn.execute(
        """
        INSERT INTO source_files
            (path, rel_path, size_bytes, mtime_ns, file_sha256, hash_mode, first_seen_at, last_seen_at, last_run_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        ON CONFLICT(path) DO UPDATE SET
            rel_path=excluded.rel_path,
            size_bytes=excluded.size_bytes,
            mtime_ns=excluded.mtime_ns,
            file_sha256=excluded.file_sha256,
            hash_mode=excluded.hash_mode,
            last_seen_at=excluded.last_seen_at,
            last_run_id=excluded.last_run_id,
            status='active'
        """,
        (str(path), rel_path, stat.st_size, stat.st_mtime_ns, file_hash, hash_mode, now, now, run_id),
    )
    row = conn.execute("SELECT id FROM source_files WHERE path=?", (str(path),)).fetchone()
    if row is None:
        raise RuntimeError(f"Could not upsert source file: {path}")
    return int(row[0])


def upsert_page(
    conn: sqlite3.Connection,
    source_file_id: int,
    page_index: int,
    frame: Image.Image,
    file_hash: str,
    do_ocr: bool,
    lang: str,
    psm: int,
) -> str:
    frame_copy = frame.copy()
    pix_hash = pixel_sha256(frame_copy)
    near_hash = dhash64(frame_copy)
    old = conn.execute(
        """
        SELECT pixel_sha256, page_content_sha256, ocr_sha256, ocr_confidence, ocr_text
        FROM tiff_pages
        WHERE source_file_id=? AND page_index=?
        """,
        (source_file_id, page_index),
    ).fetchone()

    text = ""
    conf: Optional[float] = None
    ocr_hash: Optional[str] = None
    if do_ocr:
        # Avoid re-running OCR when the normalized pixels have not changed.
        if old is not None and old[0] == pix_hash and old[2]:
            ocr_hash = str(old[2])
            conf = old[3]
            text = old[4] or ""
        else:
            text, conf = ocr_page(frame_copy, lang=lang, psm=psm)
            ocr_hash = sha256_text(text)

    content_hash = canonical_json_hash(
        {
            "hash_version": 1,
            "pixel_sha256": pix_hash,
            "ocr_sha256": ocr_hash or "",
        }
    )

    if old is None:
        change_status = "new"
    elif old[1] == content_hash:
        change_status = "unchanged"
    else:
        change_status = "changed"

    now = utc_now()
    conn.execute(
        """
        INSERT INTO tiff_pages
            (source_file_id, page_index, width_px, height_px, mode, file_sha256,
             pixel_sha256, dhash64, ocr_sha256, ocr_confidence, ocr_text,
             page_content_sha256, created_at, updated_at, change_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_file_id, page_index) DO UPDATE SET
            width_px=excluded.width_px,
            height_px=excluded.height_px,
            mode=excluded.mode,
            file_sha256=excluded.file_sha256,
            pixel_sha256=excluded.pixel_sha256,
            dhash64=excluded.dhash64,
            ocr_sha256=excluded.ocr_sha256,
            ocr_confidence=excluded.ocr_confidence,
            ocr_text=excluded.ocr_text,
            page_content_sha256=excluded.page_content_sha256,
            updated_at=excluded.updated_at,
            change_status=excluded.change_status
        """,
        (
            source_file_id,
            page_index,
            frame_copy.width,
            frame_copy.height,
            frame_copy.mode,
            file_hash,
            pix_hash,
            near_hash,
            ocr_hash,
            conf,
            text,
            content_hash,
            now,
            now,
            change_status,
        ),
    )
    return change_status


def iter_tiffs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES)


def process_tiff(
    conn: sqlite3.Connection,
    root: Path,
    path: Path,
    args: argparse.Namespace,
    run_id: int,
) -> tuple[int, dict[str, int]]:
    if args.no_file_hash:
        file_hash = quick_file_fingerprint(path)
        hash_mode = "quick"
    else:
        file_hash = sha256_file(path)
        hash_mode = "sha256"
    source_id = upsert_source_file(conn, root, path, file_hash, hash_mode, run_id)
    counts = {"new": 0, "changed": 0, "unchanged": 0}
    frame_count = 0
    with Image.open(path) as img:
        for page_index, frame in enumerate(ImageSequence.Iterator(img), start=1):
            status = upsert_page(
                conn=conn,
                source_file_id=source_id,
                page_index=page_index,
                frame=frame,
                file_hash=file_hash,
                do_ocr=args.ocr,
                lang=args.lang,
                psm=args.psm,
            )
            counts[status] += 1
            frame_count += 1
            if args.limit_pages and frame_count >= args.limit_pages:
                break
    conn.execute("UPDATE source_files SET frame_count=? WHERE id=?", (frame_count, source_id))
    return frame_count, counts


def record_error(conn: sqlite3.Connection, run_id: int, root: Path, path: Path, exc: BaseException) -> None:
    conn.execute(
        """
        INSERT INTO inventory_errors(run_id, path, rel_path, error_type, error_message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(run_id), str(path), safe_rel_path(path, root), type(exc).__name__, str(exc), utc_now()),
    )


def mark_missing_files(conn: sqlite3.Connection, root: Path, run_id: int) -> int:
    now = utc_now()
    cur = conn.execute(
        """
        UPDATE source_files
        SET status='missing', last_seen_at=?
        WHERE status='active'
          AND last_run_id IS NOT ?
          AND path LIKE ?
        """,
        (now, run_id, str(root) + "%"),
    )
    return int(cur.rowcount if cur.rowcount is not None else 0)


def print_duplicate_report(conn: sqlite3.Connection, max_rows: int = 20) -> None:
    rows = conn.execute(
        """
        SELECT page_content_sha256, COUNT(*) AS n
        FROM tiff_pages
        GROUP BY page_content_sha256
        HAVING COUNT(*) > 1
        ORDER BY n DESC
        LIMIT ?
        """,
        (max_rows,),
    ).fetchall()
    if not rows:
        print("Duplicate exact page-content groups: 0")
        return
    print(f"Duplicate exact page-content groups: {len(rows)} shown")
    for content_hash, n in rows:
        examples = conn.execute(
            """
            SELECT sf.rel_path, tp.page_index
            FROM tiff_pages tp
            JOIN source_files sf ON sf.id = tp.source_file_id
            WHERE tp.page_content_sha256=?
            ORDER BY sf.rel_path, tp.page_index
            LIMIT 5
            """,
            (content_hash,),
        ).fetchall()
        ex = ", ".join(f"{rel}#p{page}" for rel, page in examples)
        print(f"  {content_hash[:16]}... count={n}: {ex}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 0 hash/inventory crawler for TIFF pages.")
    parser.add_argument("--root", type=Path, required=True, help="Directory containing .tif/.tiff files.")
    parser.add_argument("--db", type=Path, default=Path("local_data/db/tiff_inventory_hashes.db"))
    parser.add_argument("--ocr", action="store_true", help="Optional full-page pytesseract OCR. Usually leave off.")
    parser.add_argument("--tesseract-cmd", default=None, help="Optional path to tesseract.exe when --ocr is used.")
    parser.add_argument("--lang", default="eng", help="Tesseract language, default: eng.")
    parser.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode, default: 6.")
    parser.add_argument("--limit-files", type=int, default=0, help="Debug limit: process only N files.")
    parser.add_argument("--limit-pages", type=int, default=0, help="Debug limit: process only N pages per TIFF.")
    parser.add_argument("--no-file-hash", action="store_true", help="Quick mode: use size/mtime fingerprint instead of SHA-256 file hash.")
    parser.add_argument("--mark-missing", action="store_true", help="Mark previously active files under root missing if not seen this run.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    if not root.exists() or not root.is_dir():
        print(f"[error] root directory not found: {root}", file=sys.stderr)
        return 2
    if args.ocr:
        if pytesseract is None:
            print("[error] --ocr was supplied but pytesseract is not importable.", file=sys.stderr)
            return 2
        if args.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = args.tesseract_cmd

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    init_db(conn)

    paths = iter_tiffs(root)
    if args.limit_files:
        paths = paths[: args.limit_files]
    if not paths:
        print(f"[error] no .tif/.tiff files found under {root}", file=sys.stderr)
        return 1

    mode = "quick" if args.no_file_hash else "hash"
    if args.ocr:
        mode += "+ocr"
    started = utc_now()
    cur = conn.execute("INSERT INTO crawl_runs(root, started_at, mode) VALUES (?, ?, ?)", (str(root), started, mode))
    run_id = int(cur.lastrowid)

    files_seen = 0
    pages_seen = 0
    errors = 0
    totals = {"new": 0, "changed": 0, "unchanged": 0}

    for i, path in enumerate(paths, start=1):
        rel = safe_rel_path(path, root)
        print(f"[{i}/{len(paths)}] {rel}")
        try:
            page_count, counts = process_tiff(conn, root, path.resolve(), args, run_id)
            conn.commit()
            files_seen += 1
            pages_seen += page_count
            for key in totals:
                totals[key] += counts[key]
            print(f"  pages={page_count} new={counts['new']} changed={counts['changed']} unchanged={counts['unchanged']}")
        except (UnidentifiedImageError, OSError, RuntimeError, ValueError) as exc:
            conn.rollback()
            errors += 1
            record_error(conn, run_id, root, path.resolve(), exc)
            conn.commit()
            print(f"  [FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)

    missing_count = 0
    if args.mark_missing:
        missing_count = mark_missing_files(conn, root, run_id)

    conn.execute(
        "UPDATE crawl_runs SET finished_at=?, files_seen=?, pages_seen=?, errors=? WHERE id=?",
        (utc_now(), files_seen, pages_seen, errors, run_id),
    )
    conn.commit()

    print("=" * 60)
    print(f"Crawl complete: files={files_seen}, pages={pages_seen}, errors={errors}")
    print(f"Page status: new={totals['new']}, changed={totals['changed']}, unchanged={totals['unchanged']}")
    if args.mark_missing:
        print(f"Files marked missing: {missing_count}")
    print_duplicate_report(conn)
    print(f"DB: {args.db.resolve()}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
