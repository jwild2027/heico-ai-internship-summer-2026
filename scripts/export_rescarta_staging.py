#!/usr/bin/env python3
"""Create a ResCarta staging package from a manual group manifest.

This does not claim to be ResCarta's final archive/XML format. It creates a
clean staging package that we can compare with ResCarta Toolkit output:

  output_dir/<manual_id>/
    manifest.json
    metadata.json
    pages/000001_00000001.tif
    ocr/000001_00000001.txt

The next integration step is mapping this package to ResCarta Toolkit import
or to ResCarta-generated object folders.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export manual group manifest to ResCarta staging folders")
    parser.add_argument("--manifest", required=True, help="manual_groups.json from group_tiff_manuals.py")
    parser.add_argument("--output-dir", required=True, help="Directory for staging package output")
    parser.add_argument("--copy-pages", action="store_true", help="Copy TIFF files into the staging package")
    return parser.parse_args()


def _safe_name(value: str) -> str:
    import re
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return name or "page"


def export_manual(manual: dict, output_root: Path, *, copy_pages: bool) -> Path:
    manual_id = manual.get("manual_id") or "manual"
    manual_dir = output_root / _safe_name(str(manual_id))
    pages_dir = manual_dir / "pages"
    ocr_dir = manual_dir / "ocr"
    pages_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "manual_id": manual.get("manual_id"),
        "publication_number": manual.get("publication_number"),
        "manufacturer": manual.get("manufacturer"),
        "manual_title": manual.get("manual_title"),
        "component_title": manual.get("component_title"),
        "ata_code": manual.get("ata_code"),
        "page_count": manual.get("page_count"),
        "source_folder": manual.get("source_folder"),
    }
    (manual_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (manual_dir / "manifest.json").write_text(json.dumps(manual, indent=2, ensure_ascii=False), encoding="utf-8")

    for page in manual.get("pages") or []:
        seq = int(page.get("page_sequence") or 0)
        file_name = str(page.get("file_name") or f"page_{seq}.tif")
        stem = Path(file_name).stem
        safe_page_name = f"{seq:06d}_{_safe_name(file_name)}"

        page_metadata = {
            key: page.get(key)
            for key in [
                "file_id",
                "file_name",
                "source_path",
                "page_sequence",
                "detected_type",
                "publication_number",
                "page_document_code",
                "section_title",
                "figure_title",
                "figure_number",
                "effectivity",
                "ata_code",
                "page_number",
                "page_label",
                "issue_date",
                "revision_date",
                "revision_label",
                "citation_label",
            ]
        }
        (ocr_dir / f"{seq:06d}_{_safe_name(stem)}.metadata.json").write_text(
            json.dumps(page_metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (ocr_dir / f"{seq:06d}_{_safe_name(stem)}.txt").write_text(page.get("ocr_text") or "", encoding="utf-8")

        if copy_pages:
            src = Path(str(page.get("source_path") or ""))
            if src.exists():
                shutil.copy2(src, pages_dir / safe_page_name)
            else:
                (pages_dir / f"{safe_page_name}.missing.txt").write_text(
                    f"Source TIFF not found: {src}\n",
                    encoding="utf-8",
                )
    return manual_dir


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    output_root = Path(args.output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_root.mkdir(parents=True, exist_ok=True)

    exported = []
    for manual in manifest.get("manuals") or []:
        exported.append(export_manual(manual, output_root, copy_pages=args.copy_pages))

    print(f"Exported {len(exported)} manual staging package(s) to {output_root}")
    for path in exported:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
