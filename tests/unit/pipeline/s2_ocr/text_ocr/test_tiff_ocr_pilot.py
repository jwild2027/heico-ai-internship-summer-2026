from __future__ import annotations

from pathlib import Path
import json
import zipfile

from tiff.ocr_pilot import run_ocr_pilot, source_pages_from_zip, source_pages_from_export


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_zip_source_selection_and_no_engine(tmp_path: Path) -> None:
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("00000002.tif", b"fake")
        zf.writestr("00000001.tif", b"fake")
        zf.writestr("metadata.xml", "<metadata />")

    pages = source_pages_from_zip(zip_path, limit=2)
    assert [p.source_name for p in pages] == ["00000001.tif", "00000002.tif"]

    summary = run_ocr_pilot(zip_path=zip_path, output_dir=tmp_path / "pilot", limit=2, engine="none")
    assert summary.status == "NEEDS ATTENTION"
    assert summary.pages_selected == 2
    assert summary.missing_ocr_engine == 2
    assert Path(summary.files_written["manifest"]).exists()
    assert Path(summary.files_written["page_index"]).exists()


def test_existing_ocr_from_export_copies_and_classifies(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    page_dir = tmp_path / "pages"
    ocr_dir = tmp_path / "ocr"
    tiff = page_dir / "000001.tif"
    ocr = ocr_dir / "000001.txt"
    _write(tiff, "not a real tif but copyable")
    _write(ocr, "FIGURE 1 PARTS LIST\n120-37313-001 HOLDER, MAGAZINE\nINSTALL REPAIR SEAT ASSEMBLY FASTENER\nMORE PARTS LIST TEXT")
    export_dir.mkdir(parents=True)
    (export_dir / "page_index.json").write_text(
        json.dumps({"pages": [{"page_id": "p1", "source_image_path": str(tiff), "ocr_text_path": str(ocr), "ata_code": "25-21-00"}]}),
        encoding="utf-8",
    )

    pages = source_pages_from_export(export_dir, repo_root=tmp_path)
    assert pages[0].page_id == "p1"
    assert pages[0].existing_ocr_path == str(ocr)

    summary = run_ocr_pilot(export_dir=export_dir, output_dir=tmp_path / "pilot", limit=1, engine="existing", repo_root=tmp_path)
    assert summary.status == "OK"
    assert summary.copied_existing == 1
    assert summary.by_classification
    manifest = json.loads(Path(summary.files_written["manifest"]).read_text(encoding="utf-8"))
    assert manifest[0]["status"] == "copied_existing"
    assert manifest[0]["visible_chars"] > 0


def test_cached_outputs_are_reused(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    page_dir = tmp_path / "pages"
    ocr_dir = tmp_path / "ocr"
    tiff = page_dir / "000001.tif"
    ocr = ocr_dir / "000001.txt"
    _write(tiff, "not a real tif but copyable")
    _write(ocr, "FIGURE 1 PARTS LIST\n120-37313-001 HOLDER, MAGAZINE\nINSTALL REPAIR SEAT ASSEMBLY FASTENER")
    export_dir.mkdir(parents=True)
    (export_dir / "page_index.json").write_text(
        json.dumps({"pages": [{"page_id": "p1", "source_image_path": str(tiff), "ocr_text_path": str(ocr)}]}),
        encoding="utf-8",
    )

    first = run_ocr_pilot(export_dir=export_dir, output_dir=tmp_path / "pilot", limit=1, engine="existing", repo_root=tmp_path)
    second = run_ocr_pilot(export_dir=export_dir, output_dir=tmp_path / "pilot", limit=1, engine="existing", repo_root=tmp_path)
    assert first.copied_existing == 1
    assert second.cached_existing == 1
    assert second.status == "OK"
