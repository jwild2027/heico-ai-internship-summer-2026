from __future__ import annotations

import json
from pathlib import Path

from tiff.document_organization_inspector import inspect_export, write_inspection_json


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_export(root: Path) -> None:
    write_json(root / "organization_summary.json", {"manuals": 1, "pages": 2, "parts": 1})
    write_json(root / "page_index.json", {"pages": [
        {"page_id": "p1", "manual": "M1", "ata": "25-21-00", "page_label": "1", "rescarta_url": "http://local/p1"},
        {"page_id": "p2", "manual": "M1", "ata": "25-21-00", "page_label": "2"},
    ]})
    write_json(root / "part_tree.json", {"parts": [
        {"part_number": "120-37313-001", "nomenclature": "HOLDER, MAGAZINE", "pages": ["p1", "p2"], "mention_count": 2}
    ]})
    write_json(root / "ata_tree.json", {"ata_groups": [{"ata": "25-21-00", "manual": "M1", "pages": ["p1", "p2"]}]})
    write_json(root / "manual_ata_tree.json", {"manuals": [{"manual": "M1", "ata_groups": []}]})


def test_inspect_export_ok(tmp_path: Path) -> None:
    make_export(tmp_path)
    result = inspect_export(tmp_path, sample_parts=["120-37313-001"], sample_pages=["p1"], sample_atas=["25-21-00"])
    assert result.ok
    assert result.page_count == 2
    assert result.part_count == 1
    assert result.ata_group_count == 1
    assert result.sample_parts[0]["part_number"] == "120-37313-001"


def test_missing_file_is_error(tmp_path: Path) -> None:
    make_export(tmp_path)
    (tmp_path / "part_tree.json").unlink()
    result = inspect_export(tmp_path)
    assert not result.ok
    assert any("part_tree.json" in err for err in result.errors)


def test_missing_sample_part_is_error(tmp_path: Path) -> None:
    make_export(tmp_path)
    result = inspect_export(tmp_path, sample_parts=["MISSING-PART"])
    assert not result.ok
    assert any("MISSING-PART" in err for err in result.errors)


def test_write_inspection_json(tmp_path: Path) -> None:
    make_export(tmp_path / "export")
    result = inspect_export(tmp_path / "export")
    out = write_inspection_json(result, tmp_path / "out" / "inspection.json")
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "OK"


def test_inspector_accepts_backend_ata_aliases(tmp_path: Path) -> None:
    write_json(tmp_path / "organization_summary.json", {"manuals": 1, "pages": 1, "parts": 1})
    write_json(tmp_path / "page_index.json", {"pages": [
        {"page_id": "p1", "publication_number": "Manual One", "ata_code": "25-21-00", "page_label": "1"}
    ]})
    write_json(tmp_path / "part_tree.json", {"parts": [
        {"part_number": "120-1", "nomenclature": "TEST", "pages": ["p1"], "mention_count": 1}
    ]})
    write_json(tmp_path / "ata_tree.json", {"ata_groups": [
        {"manual_id": "m1", "publication_number": "Manual One", "ata_code": "25-21-00", "page_ids": ["p1"]}
    ]})
    write_json(tmp_path / "manual_ata_tree.json", {"manuals": [
        {"manual_id": "m1", "publication_number": "Manual One", "ata_groups": []}
    ]})

    result = inspect_export(tmp_path, sample_atas=["25-21-00"], sample_pages=["p1"])
    assert result.ok
    assert result.sample_ata[0]["manual"] == "Manual One"
    assert result.sample_pages[0]["manual"] == "Manual One"
