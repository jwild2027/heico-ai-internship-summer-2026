from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

TIFF_EXTENSIONS = {".tif", ".tiff"}


def _normalize_hash_mode(hash_mode: str) -> str:
    value = (hash_mode or "stat").strip().lower()
    if value in {"sha256", "hash", "content", "file"}:
        return "content"
    if value in {"stat", "mtime", "size"}:
        return "stat"
    raise ValueError("hash_mode must be 'stat', 'content', or 'sha256'")


class ChangedPathList(list[str]):
    """List that remains compatible with older tests comparing to tuples."""

    def __eq__(self, other):  # type: ignore[override]
        if isinstance(other, tuple):
            return tuple(self) == other
        return super().__eq__(other)


@dataclass(frozen=True)
class FileSnapshot:
    """A point-in-time fingerprint of one TIFF source file."""

    rel_path: str
    abs_path: str
    size_bytes: int
    mtime_ns: int
    fingerprint: str


@dataclass
class ChangeDetectionSummary:
    """Result of an incremental file scan.

    This object is independent of DB commit. A caller can inspect or dry-run the
    result and only call commit_summary() after OCR/backend processing succeeds.
    """

    files_seen: int = 0
    new_files: int = 0
    changed_files: int = 0
    unchanged_files: int = 0
    missing_files: int = 0
    changed_paths: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)
    snapshots: list[FileSnapshot] = field(default_factory=list)
    scanned_at: float = field(default_factory=time.time)

    @property
    def changed_list_count(self) -> int:
        return len(self.changed_paths)

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_paths or self.missing_paths)


@dataclass
class ChangedTiffListResult:
    """Compatibility result returned by build_changed_tiff_list()."""

    summary: ChangeDetectionSummary
    changed_list_path: str
    state_db_path: str
    state_committed: bool
    changed_list_written: bool


class IncrementalStateDB:
    """SQLite-backed state store for incremental TIFF change detection."""

    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        self.ensure_schema(conn)
        return conn

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incremental_file_state (
                rel_path TEXT PRIMARY KEY,
                abs_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,
                last_seen_at REAL NOT NULL,
                committed_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incremental_pipeline_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at REAL NOT NULL,
                committed_at REAL,
                files_seen INTEGER NOT NULL,
                new_files INTEGER NOT NULL,
                changed_files INTEGER NOT NULL,
                unchanged_files INTEGER NOT NULL,
                missing_files INTEGER NOT NULL,
                changed_list_count INTEGER NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.commit()

    def reset(self) -> None:
        conn = self.connect()
        try:
            conn.execute("DELETE FROM incremental_file_state")
            conn.execute("DELETE FROM incremental_pipeline_runs")
            conn.commit()
        finally:
            conn.close()

    def iter_tiff_paths(self, root: str | os.PathLike[str]) -> list[Path]:
        root_path = Path(root)
        if not root_path.exists():
            return []
        return sorted(
            p for p in root_path.rglob("*") if p.is_file() and p.suffix.lower() in TIFF_EXTENSIONS
        )

    def snapshot_file(
        self,
        path: str | os.PathLike[str],
        root: str | os.PathLike[str],
        hash_mode: str = "stat",
    ) -> FileSnapshot:
        root_path = Path(root).resolve()
        file_path = Path(path).resolve()
        st = file_path.stat()
        rel_path = file_path.relative_to(root_path).as_posix()
        normalized_mode = _normalize_hash_mode(hash_mode)
        if normalized_mode == "content":
            digest = hashlib.sha256()
            with file_path.open("rb") as fh:
                for block in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(block)
            fingerprint = "sha256:" + digest.hexdigest()
        else:
            fingerprint = f"stat:{st.st_size}:{st.st_mtime_ns}"
        return FileSnapshot(
            rel_path=rel_path,
            abs_path=str(file_path),
            size_bytes=int(st.st_size),
            mtime_ns=int(st.st_mtime_ns),
            fingerprint=fingerprint,
        )

    def detect_changes(
        self,
        root: str | os.PathLike[str],
        hash_mode: str = "stat",
    ) -> ChangeDetectionSummary:
        """Detect new/changed/missing TIFFs without committing state.

        Important Windows behavior: sqlite3.Connection as a context manager does
        not close the connection; it only commits/rolls back the transaction.
        Dry-run/preview tests remove the temporary DB if no commit occurs, so we
        explicitly close connections before returning.
        """
        summary = ChangeDetectionSummary(scanned_at=time.time())
        root_path = Path(root).resolve()
        conn = self.connect()
        try:
            previous = {
                row["rel_path"]: row
                for row in conn.execute("SELECT * FROM incremental_file_state").fetchall()
            }
        finally:
            conn.close()

        current_rel_paths: set[str] = set()
        for path in self.iter_tiff_paths(root_path):
            snap = self.snapshot_file(path, root_path, hash_mode=hash_mode)
            summary.snapshots.append(snap)
            summary.files_seen += 1
            current_rel_paths.add(snap.rel_path)
            old = previous.get(snap.rel_path)
            if old is None:
                summary.new_files += 1
                summary.changed_paths.append(snap.abs_path)
            elif old["fingerprint"] != snap.fingerprint:
                summary.changed_files += 1
                summary.changed_paths.append(snap.abs_path)
            else:
                summary.unchanged_files += 1

        for rel_path in sorted(set(previous) - current_rel_paths):
            summary.missing_files += 1
            summary.missing_paths.append(rel_path)

        return summary

    # Compatibility alias for older scripts/tests that used scan() naming.
    def scan(self, root: str | os.PathLike[str], hash_mode: str = "stat") -> ChangeDetectionSummary:
        return self.detect_changes(root, hash_mode=hash_mode)

    def commit_summary(self, summary: ChangeDetectionSummary, status: str = "committed") -> None:
        """Commit a scan summary after downstream work has succeeded."""
        committed_at = time.time()
        conn = self.connect()
        try:
            for snap in summary.snapshots:
                conn.execute(
                    """
                    INSERT INTO incremental_file_state
                        (rel_path, abs_path, size_bytes, mtime_ns, fingerprint, last_seen_at, committed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(rel_path) DO UPDATE SET
                        abs_path=excluded.abs_path,
                        size_bytes=excluded.size_bytes,
                        mtime_ns=excluded.mtime_ns,
                        fingerprint=excluded.fingerprint,
                        last_seen_at=excluded.last_seen_at,
                        committed_at=excluded.committed_at
                    """,
                    (
                        snap.rel_path,
                        snap.abs_path,
                        snap.size_bytes,
                        snap.mtime_ns,
                        snap.fingerprint,
                        summary.scanned_at,
                        committed_at,
                    ),
                )
            for rel_path in summary.missing_paths:
                conn.execute("DELETE FROM incremental_file_state WHERE rel_path = ?", (rel_path,))
            conn.execute(
                """
                INSERT INTO incremental_pipeline_runs
                    (started_at, committed_at, files_seen, new_files, changed_files, unchanged_files,
                     missing_files, changed_list_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.scanned_at,
                    committed_at,
                    summary.files_seen,
                    summary.new_files,
                    summary.changed_files,
                    summary.unchanged_files,
                    summary.missing_files,
                    summary.changed_list_count,
                    status,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def write_changed_list(paths: Sequence[str], output_path: str | os.PathLike[str]) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(str(p) for p in paths)
    if text:
        text += "\n"
    out.write_text(text, encoding="utf-8")


def read_changed_list(path: str | os.PathLike[str]) -> ChangedPathList:
    p = Path(path)
    if not p.exists():
        return ChangedPathList()
    return ChangedPathList(
        [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    )


def build_changed_tiff_list(
    *,
    root: str | os.PathLike[str],
    state_db_path: str | os.PathLike[str],
    changed_list_path: str | os.PathLike[str],
    hash_mode: str = "stat",
    persist: bool | None = None,
    commit_state: bool | None = None,
    write_list: bool | None = None,
) -> ChangedTiffListResult:
    """Compatibility helper used by older tests/scripts.

    Defaults preserve the original behavior: write changed_tiffs.txt and commit
    file state immediately. Newer pipeline code should prefer detect_changes()
    plus commit_summary() after downstream work succeeds.
    """
    if persist is not None:
        default_commit = bool(persist)
        default_write = bool(persist)
    else:
        default_commit = True
        default_write = True
    do_commit = default_commit if commit_state is None else bool(commit_state)
    do_write = default_write if write_list is None else bool(write_list)

    state_path = Path(state_db_path)
    state_existed_before = state_path.exists()
    state = IncrementalStateDB(state_path)
    summary = state.detect_changes(root, hash_mode=hash_mode)
    if do_write:
        write_changed_list(summary.changed_paths, changed_list_path)
    if do_commit:
        state.commit_summary(summary)
    elif not state_existed_before:
        # detect_changes() may open SQLite to read previous state. For preview/dry-run
        # compatibility, remove the empty DB files it created when no commit is requested.
        for suffix in ("", "-journal", "-wal", "-shm"):
            candidate = Path(str(state_path) + suffix)
            if candidate.exists():
                try:
                    candidate.unlink()
                except OSError:
                    pass
    return ChangedTiffListResult(
        summary=summary,
        changed_list_path=str(changed_list_path),
        state_db_path=str(state_db_path),
        state_committed=do_commit,
        changed_list_written=do_write,
    )
