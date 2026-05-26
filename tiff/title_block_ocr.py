"""Local title-block OCR helpers for TIFF drawings.

This module deliberately uses the local ``tesseract`` command-line executable
instead of a cloud OCR API. It crops a few likely title/header regions from the
first TIFF page, preprocesses those crops, runs Tesseract locally, and returns a
JSON-ready OCR result.

The OCR output is a hint for metadata extraction; the source TIFF remains the
authoritative record.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageOps


@dataclass(frozen=True)
class OCRRegionResult:
    """OCR output for one cropped image region."""

    region_name: str
    page_index: int
    bbox: tuple[int, int, int, int]
    status: str
    text: str
    char_count: int
    error: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TitleBlockOCRResult:
    """OCR output for likely title-block/header regions."""

    enabled: bool
    status: str
    engine: str
    tesseract_path: Optional[str]
    lang: str
    page_index: int
    best_region: Optional[str]
    combined_text: str
    regions: list[OCRRegionResult]
    error: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["regions"] = [region.to_dict() for region in self.regions]
        return data


def normalize_tesseract_candidates(tesseract_cmd: str | None = None) -> list[str]:
    r"""Return possible Tesseract executable paths for a user-supplied value.

    This accepts the formats people commonly paste into Git Bash/Streamlit:

    - C:\Program Files\Tesseract-OCR\tesseract.exe
    - C:/Program Files/Tesseract-OCR/tesseract.exe
    - /c/Program Files/Tesseract-OCR/tesseract.exe
    - "C:\Program Files\Tesseract-OCR\tesseract.exe"
    - C:\Program Files\Tesseract-OCR

    It does not call external services. It only normalizes local paths.
    """

    raw_candidates: list[str] = []
    if tesseract_cmd:
        raw_candidates.append(tesseract_cmd)
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd:
        raw_candidates.append(env_cmd)

    raw_candidates.extend(
        [
            "tesseract",
            "tesseract.exe",
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
    )

    expanded: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if not value:
            return
        cleaned = os.path.expandvars(str(value).strip()).strip('"').strip("'").strip()
        if not cleaned:
            return

        variants = [cleaned]

        # Git Bash/MSYS style path: /c/Program Files/... -> C:\Program Files\...
        match = re.match(r"^/([A-Za-z])/(.+)$", cleaned)
        if match:
            drive = match.group(1).upper()
            rest = match.group(2).replace("/", "\\")
            variants.append(f"{drive}:\\{rest}")

        # If the user pasted doubled backslashes literally, also try single backslashes.
        if "\\\\" in cleaned:
            variants.append(cleaned.replace("\\\\", "\\"))

        # If the user supplied the install directory instead of the executable.
        for variant in list(variants):
            lower = variant.lower().replace("/", "\\")
            if not lower.endswith("tesseract.exe") and not lower.endswith("tesseract"):
                variants.append(str(Path(variant) / "tesseract.exe"))

        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                expanded.append(variant)

    for candidate in raw_candidates:
        add(candidate)

    return expanded


def find_tesseract(tesseract_cmd: str | None = None) -> Optional[str]:
    """Return a local Tesseract executable path, if one is available."""

    for candidate in normalize_tesseract_candidates(tesseract_cmd):
        found = shutil.which(candidate)
        if found:
            return found

        candidate_path = Path(candidate)
        if candidate_path.exists() and candidate_path.is_file():
            return str(candidate_path)

    return None


def title_block_boxes(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Return likely drawing title/header crop boxes for a page.

    Many engineering drawings place the title block in the bottom-right corner,
    but some have banners at the top or long strips at the bottom. We OCR a few
    targeted regions instead of the entire drawing first.
    """

    width = int(width)
    height = int(height)
    return [
        ("bottom_right_title_block", (int(width * 0.50), int(height * 0.58), width, height)),
        ("bottom_strip", (0, int(height * 0.70), width, height)),
        ("top_strip", (0, 0, width, int(height * 0.18))),
        ("right_strip", (int(width * 0.68), 0, width, height)),
    ]


def _sanitize_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    left = max(0, min(int(left), width - 1))
    top = max(0, min(int(top), height - 1))
    right = max(left + 1, min(int(right), width))
    bottom = max(top + 1, min(int(bottom), height))
    return left, top, right, bottom


def preprocess_for_ocr(image: Image.Image, *, max_width: int = 3200) -> Image.Image:
    """Convert an image crop into a Tesseract-friendly image."""

    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)

    # Upscale small crops so title-block text has enough pixels for OCR.
    width, height = gray.size
    if width < 1200:
        scale = min(3.0, 1200 / max(width, 1))
        gray = gray.resize((int(width * scale), int(height * scale)))
        width, height = gray.size

    # Downscale extremely wide crops to avoid slow OCR on huge scans.
    if width > max_width:
        scale = max_width / width
        gray = gray.resize((max_width, max(1, int(height * scale))))

    # Light thresholding works well for bitonal drawings and scanned title blocks.
    return gray.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")


def _decode_tesseract_output(value: bytes | str | None) -> str:
    """Decode Tesseract output without crashing on Windows code-page bytes.

    On Windows, ``subprocess.run(..., text=True)`` uses the active locale
    encoding, often cp1252. Some OCR output contains bytes that are invalid
    for that codec, which can raise ``UnicodeDecodeError`` inside a subprocess
    reader thread. We capture bytes and decode with replacement instead.
    """

    if value is None:
        return ""
    if isinstance(value, str):
        return value

    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue

    return value.decode("utf-8", errors="replace")


def run_tesseract_on_image(
    image_path: str | Path,
    *,
    tesseract_path: str,
    lang: str = "eng",
    psm: int = 6,
    timeout_seconds: int = 30,
) -> tuple[str, Optional[str]]:
    """Run local Tesseract on one image and return ``(text, error)``."""

    cmd = [
        tesseract_path,
        str(image_path),
        "stdout",
        "--psm",
        str(psm),
        "-l",
        lang,
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return "", f"Tesseract timed out after {timeout_seconds} seconds"
    except OSError as exc:
        return "", str(exc)

    text = _decode_tesseract_output(proc.stdout).strip()
    error = _decode_tesseract_output(proc.stderr).strip() or None
    if proc.returncode != 0:
        return text, error or f"Tesseract exited with code {proc.returncode}"
    return text, error


def _open_tiff_page(path: Path, page_index: int) -> Image.Image:
    image = Image.open(path)
    if page_index:
        image.seek(page_index)
    return image.copy()


def run_title_block_ocr(
    tiff_path: str | Path,
    *,
    page_index: int = 0,
    lang: str = "eng",
    tesseract_cmd: str | None = None,
    timeout_seconds: int = 30,
) -> TitleBlockOCRResult:
    """OCR likely title-block/header regions from a TIFF file.

    Args:
        tiff_path: Path to a .tif or .tiff file.
        page_index: Zero-based page index to OCR. Most drawings use page 0.
        lang: Tesseract language code, usually ``eng``.
        tesseract_cmd: Optional explicit path to tesseract.exe.
        timeout_seconds: Timeout per crop region.
    """

    path = Path(tiff_path)
    tesseract_path = find_tesseract(tesseract_cmd)
    if not tesseract_path:
        return TitleBlockOCRResult(
            enabled=True,
            status="tesseract_not_found",
            engine="tesseract",
            tesseract_path=None,
            lang=lang,
            page_index=page_index,
            best_region=None,
            combined_text="",
            regions=[],
            error="Tesseract was not found. Install it locally or set TESSERACT_CMD.",
        )

    try:
        page = _open_tiff_page(path, page_index)
    except Exception as exc:  # pragma: no cover - defensive, depends on source file
        return TitleBlockOCRResult(
            enabled=True,
            status="read_error",
            engine="tesseract",
            tesseract_path=tesseract_path,
            lang=lang,
            page_index=page_index,
            best_region=None,
            combined_text="",
            regions=[],
            error=str(exc),
        )

    width, height = page.size
    region_results: list[OCRRegionResult] = []

    with tempfile.TemporaryDirectory(prefix="heico_tiff_ocr_") as tmp_dir:
        tmp = Path(tmp_dir)
        for region_name, raw_box in title_block_boxes(width, height):
            box = _sanitize_box(raw_box, width, height)
            crop = page.crop(box)
            processed = preprocess_for_ocr(crop)
            image_path = tmp / f"{region_name}.png"
            processed.save(image_path)
            text, error = run_tesseract_on_image(
                image_path,
                tesseract_path=tesseract_path,
                lang=lang,
                psm=6,
                timeout_seconds=timeout_seconds,
            )
            normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            region_results.append(
                OCRRegionResult(
                    region_name=region_name,
                    page_index=page_index,
                    bbox=box,
                    status="ok" if normalized else "empty",
                    text=normalized,
                    char_count=len(normalized),
                    error=error,
                )
            )

    non_empty = [region for region in region_results if region.text]
    best = max(non_empty, key=lambda region: region.char_count, default=None)
    combined_parts = [
        f"[{region.region_name}]\n{region.text}"
        for region in region_results
        if region.text
    ]
    combined_text = "\n\n".join(combined_parts)

    if best is None:
        status = "no_text_found"
    elif len(non_empty) < len(region_results):
        status = "partial"
    else:
        status = "ok"

    return TitleBlockOCRResult(
        enabled=True,
        status=status,
        engine="tesseract",
        tesseract_path=tesseract_path,
        lang=lang,
        page_index=page_index,
        best_region=best.region_name if best else None,
        combined_text=combined_text,
        regions=region_results,
        error=None,
    )
