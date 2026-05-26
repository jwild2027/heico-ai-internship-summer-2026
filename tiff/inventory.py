"""TIFF file inventory utilities.

First TIFF milestone:
- Find .tif/.tiff files.
- Record file-system metadata.
- Read basic TIFF technical metadata with Pillow.
- Optionally hash files for duplicate detection.

This does not OCR yet. OCR and title-block parsing come after inventory.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

TIFF_SUFFIXES = {".tif", ".tiff"}


@dataclass(frozen=True)
class TIFFInventoryRecord:
    """One row of TIFF inventory metadata."""

    source_path: str
    relative_path: str
    file_name: str
    extension: str
    file_size_bytes: int
    modified_time_utc: str
    sha256: Optional[str]
    page_count: Optional[int]
    width_px: Optional[int]
    height_px: Optional[int]
    dpi_x: Optional[float]
    dpi_y: Optional[float]
    color_mode: Optional[str]
    compression: Optional[str]
    error: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def utc_from_timestamp(ts: float) -> str:
    """Convert an OS timestamp into an ISO-8601 UTC string."""

    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_tiff_files(root: Path, *, recursive: bool = True) -> Iterator[Path]:
    """Yield TIFF files under root in stable sorted order."""

    root = Path(root)
    pattern = "**/*" if recursive else "*"
    candidates = sorted(root.glob(pattern))
    for path in candidates:
        if path.is_file() and path.suffix.lower() in TIFF_SUFFIXES:
            yield path


def _safe_relative_path(path: Path, source_root: Optional[Path]) -> str:
    if source_root is None:
        return path.name
    try:
        return str(path.resolve().relative_to(source_root.resolve()))
    except ValueError:
        return path.name


def read_tiff_technical_metadata(path: Path) -> dict[str, object]:
    """Read basic TIFF image metadata.

    Pillow is used only for technical metadata here. If Pillow is not installed
    or the file cannot be opened, the returned dict contains an error string and
    null technical fields, allowing inventory to continue.
    """

    empty = {
        "page_count": None,
        "width_px": None,
        "height_px": None,
        "dpi_x": None,
        "dpi_y": None,
        "color_mode": None,
        "compression": None,
        "error": None,
    }

    try:
        from PIL import Image
    except ImportError:
        empty["error"] = "Pillow is not installed; cannot read TIFF metadata"
        return empty

    try:
        with Image.open(path) as image:
            page_count = getattr(image, "n_frames", 1)
            width_px, height_px = image.size
            dpi = image.info.get("dpi")
            dpi_x: Optional[float] = None
            dpi_y: Optional[float] = None
            if isinstance(dpi, tuple) and len(dpi) >= 2:
                dpi_x = float(dpi[0])
                dpi_y = float(dpi[1])
            elif isinstance(dpi, (int, float)):
                dpi_x = float(dpi)
                dpi_y = float(dpi)

            compression = image.info.get("compression")
            if compression is not None:
                compression = str(compression)

            return {
                "page_count": int(page_count),
                "width_px": int(width_px),
                "height_px": int(height_px),
                "dpi_x": dpi_x,
                "dpi_y": dpi_y,
                "color_mode": str(image.mode) if image.mode else None,
                "compression": compression,
                "error": None,
            }
    except Exception as exc:  # keep inventory running on damaged TIFFs
        empty["error"] = f"Failed to read TIFF metadata: {exc}"
        return empty


def build_tiff_inventory_record(
    path: Path,
    *,
    source_root: Optional[Path] = None,
    hash_file: bool = True,
) -> TIFFInventoryRecord:
    """Build an inventory record for a single TIFF file."""

    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if path.suffix.lower() not in TIFF_SUFFIXES:
        raise ValueError(f"Not a TIFF file: {path}")

    stat = path.stat()
    technical = read_tiff_technical_metadata(path)
    digest = sha256_file(path) if hash_file else None

    return TIFFInventoryRecord(
        source_path=str(path),
        relative_path=_safe_relative_path(path, source_root),
        file_name=path.name,
        extension=path.suffix.lower(),
        file_size_bytes=int(stat.st_size),
        modified_time_utc=utc_from_timestamp(stat.st_mtime),
        sha256=digest,
        page_count=technical["page_count"],
        width_px=technical["width_px"],
        height_px=technical["height_px"],
        dpi_x=technical["dpi_x"],
        dpi_y=technical["dpi_y"],
        color_mode=technical["color_mode"],
        compression=technical["compression"],
        error=technical["error"],
    )


def inventory_directory(
    root: Path,
    *,
    recursive: bool = True,
    hash_files: bool = True,
    limit: Optional[int] = None,
) -> list[TIFFInventoryRecord]:
    """Inventory TIFF files under a directory."""

    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    records: list[TIFFInventoryRecord] = []
    for index, path in enumerate(iter_tiff_files(root, recursive=recursive), start=1):
        if limit is not None and index > limit:
            break
        records.append(
            build_tiff_inventory_record(path, source_root=root, hash_file=hash_files)
        )
    return records
