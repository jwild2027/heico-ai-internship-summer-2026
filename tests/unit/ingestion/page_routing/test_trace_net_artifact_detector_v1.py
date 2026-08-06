from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.trace_net_artifact_detector_v1 import build_artifact_detector_report, parse_metadata_zip
from tiff.trace_net_artifact_detector_v1_quality import ArtifactDetectorQualityThresholds


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_metadata_zip(path: Path, page_count: int = 3) -> None:
    files = []
    pages = []
    for i in range(1, page_count + 1):
        fid = f"FID{i:04d}"
        filename = f"{i:08d}.tif"
        files.append(f'''<mets:file ID="{fid}" GROUPID="FG0001" MIMETYPE="image/tiff" SIZE="{1000+i}" CHECKSUM="abc{i}" CHECKSUMTYPE="SHA-1"><mets:FLocat LOCTYPE="URL" xlink:href="file://./{filename}" xlink:type="simple"/></mets:file>''')
        pages.append(f'''<mets:div TYPE="page" ORDER="{i}" LABEL="{i}" xlink:label="PPG{i:04d}"><mets:fptr FILEID="{fid}"/></mets:div>''')
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:mods="http://www.loc.gov/mods/v3" xmlns:xlink="http://www.w3.org/1999/xlink" LABEL="TEST MANUAL" OBJID="heico/test" TYPE="ResCarta Monograph Metadata v3.1">
  <mets:dmdSec><mets:mdWrap><mets:xmlData><mods:mods><mods:titleInfo><mods:title>TEST MANUAL</mods:title></mods:titleInfo><mods:identifier type="local">heico/test</mods:identifier></mods:mods></mets:xmlData></mets:mdWrap></mets:dmdSec>
  <mets:fileSec><mets:fileGrp>{''.join(files)}</mets:fileGrp></mets:fileSec>
  <mets:structMap TYPE="physical"><mets:div TYPE="monograph">{''.join(pages)}</mets:div></mets:structMap>
</mets:mets>'''
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("metadata.xml", xml)
        for i in range(1, page_count + 1):
            z.writestr(f"{i:08d}.tif", b"fake")


def test_parse_metadata_zip_reads_rescarta_pages(tmp_path: Path) -> None:
    metadata_zip = tmp_path / "metadata.zip"
    _write_metadata_zip(metadata_zip, page_count=3)
    doc, pages = parse_metadata_zip(metadata_zip)
    assert doc["document_label"] == "TEST MANUAL"
    assert doc["source_page_count"] == 3
    assert pages[0]["source_page_id"] == "metadata_page_000001"
    assert "00000001" in pages[0]["page_aliases"]
    assert pages[1]["image_filename"] == "00000002.tif"


def test_build_artifact_detector_report_indexes_artifacts_and_metadata(tmp_path: Path) -> None:
    root = tmp_path / "local_data" / "organization" / "trace_net"
    _write_json(root / "table_line_geometry" / "trace_net_table_line_geometry_v1.json", {
        "schema_version": "trace_net_table_line_geometry_v1",
        "quality_status": "PASS",
        "status": "TABLE_LINE_GEOMETRY_BUILT",
        "summary": {"schema_version": "trace_net_table_line_geometry_v1", "quality_status": "PASS"},
        "table_geometry_cards": [
            {"page_id": "t_p_test_p000001", "table_id": "table_1", "morphology_signal_strength": "GRID"},
            {"page_id": "t_p_test_p000002", "table_id": "table_2", "morphology_signal_strength": "WEAK_LINE_SIGNAL"},
        ],
    })
    _write_json(root / "visual_diagram" / "trace_net_visual_diagram_v1.json", {
        "schema_version": "trace_net_visual_diagram_v1",
        "quality_status": "PASS",
        "status": "VISUAL_DIAGRAM_BUILT",
        "review_cards": [{"page_id": "t_p_test_p000003", "target_id": "fig_1"}],
    })
    metadata_zip = tmp_path / "metadata.zip"
    _write_metadata_zip(metadata_zip, page_count=3)

    report = build_artifact_detector_report(
        artifact_roots=[root],
        metadata_zip=metadata_zip,
        output_dir=tmp_path / "out",
        thresholds=ArtifactDetectorQualityThresholds(
            min_artifact_cards=2,
            min_page_artifact_cards=3,
            min_source_page_cards=3,
            require_metadata_pages=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["artifact_card_count"] == 2
    assert report["summary"]["source_page_card_count"] == 3
    assert report["summary"]["table_evidence_page_count"] == 2
    assert report["summary"]["image_visual_evidence_page_count"] == 1
    assert (tmp_path / "out" / "trace_net_artifact_detector_v1.json").exists()
    page_ids = {card["page_id"] for card in report["page_artifact_cards"]}
    assert "t_p_test_p000001" in page_ids
    assert "metadata_page_000001" in page_ids


def test_unsafe_artifact_card_is_not_safe_for_routing(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    _write_json(root / "bad" / "bad.json", {
        "schema_version": "trace_net_bad_v1",
        "quality_status": "PASS",
        "summary": {"answer_permission_count": 1},
        "page_cards": [{"page_id": "p1"}],
    })
    report = build_artifact_detector_report(
        artifact_roots=[root],
        output_dir=tmp_path / "out",
        thresholds=ArtifactDetectorQualityThresholds(
            min_artifact_cards=1,
            min_page_artifact_cards=1,
            max_answer_permission_count=0,
        ),
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["unsafe_artifact_card_count"] == 1
    assert report["summary"]["unsafe_safe_for_routing_artifact_card_count"] == 0
    assert report["summary"]["safe_for_routing_answer_permission_count"] == 0
    assert report["artifact_cards"][0]["safe_for_routing"] is False
