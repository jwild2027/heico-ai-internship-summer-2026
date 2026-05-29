"""Read-only audit helper for a public ResCarta-style TIFF ZIP."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import zipfile
from typing import Any


@dataclass
class PublicTiffZipAudit:
    status: str
    zip_path: str
    total_entries: int
    total_bytes: int
    tiff_files: int
    xml_files: int
    ocr_text_files: int
    other_files: int
    has_metadata_xml: bool
    sample_tiffs: list[str] = field(default_factory=list)
    sample_xml: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "zip_path": self.zip_path,
            "total_entries": self.total_entries,
            "total_bytes": self.total_bytes,
            "tiff_files": self.tiff_files,
            "xml_files": self.xml_files,
            "ocr_text_files": self.ocr_text_files,
            "other_files": self.other_files,
            "has_metadata_xml": self.has_metadata_xml,
            "sample_tiffs": self.sample_tiffs,
            "sample_xml": self.sample_xml,
            "warnings": self.warnings,
        }


def audit_public_tiff_zip(zip_path: str | Path, sample_limit: int = 10) -> PublicTiffZipAudit:
    zip_path = Path(zip_path)
    warnings: list[str] = []
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
    tiff_names = [info.filename for info in infos if info.filename.lower().endswith((".tif", ".tiff"))]
    xml_names = [info.filename for info in infos if info.filename.lower().endswith(".xml")]
    txt_names = [info.filename for info in infos if info.filename.lower().endswith(".txt")]
    other = [info.filename for info in infos if info.filename not in set(tiff_names + xml_names + txt_names)]
    total_bytes = sum(info.file_size for info in infos)
    has_metadata_xml = any(Path(name).name.lower() == "metadata.xml" for name in xml_names)
    if not tiff_names:
        warnings.append("no TIFF files found")
    if not has_metadata_xml:
        warnings.append("metadata.xml not found")
    if not txt_names:
        warnings.append("no OCR .txt files found in ZIP; OCR may need to be imported/generated separately")
    status = "OK" if tiff_names and has_metadata_xml else "NEEDS ATTENTION"
    return PublicTiffZipAudit(
        status=status,
        zip_path=str(zip_path),
        total_entries=len(infos),
        total_bytes=total_bytes,
        tiff_files=len(tiff_names),
        xml_files=len(xml_names),
        ocr_text_files=len(txt_names),
        other_files=len(other),
        has_metadata_xml=has_metadata_xml,
        sample_tiffs=tiff_names[:sample_limit],
        sample_xml=xml_names[:sample_limit],
        warnings=warnings,
    )


def write_audit_json(audit: PublicTiffZipAudit, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit.to_jsonable(), indent=2), encoding="utf-8")


def format_public_tiff_zip_audit(audit: PublicTiffZipAudit) -> str:
    lines = [
        "Public TIFF ZIP audit",
        f"  Status: {audit.status}",
        f"  ZIP: {audit.zip_path}",
        f"  Total entries: {audit.total_entries}",
        f"  Total bytes: {audit.total_bytes}",
        "",
        "Counts:",
        f"  TIFF files: {audit.tiff_files}",
        f"  XML files: {audit.xml_files}",
        f"  OCR text files: {audit.ocr_text_files}",
        f"  Other files: {audit.other_files}",
        f"  metadata.xml present: {audit.has_metadata_xml}",
    ]
    if audit.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in audit.warnings:
            lines.append(f"  - {warning}")
    if audit.sample_tiffs:
        lines.append("")
        lines.append("Sample TIFF files:")
        for name in audit.sample_tiffs:
            lines.append(f"  {name}")
    if audit.sample_xml:
        lines.append("")
        lines.append("Sample XML files:")
        for name in audit.sample_xml:
            lines.append(f"  {name}")
    return "\n".join(lines)
