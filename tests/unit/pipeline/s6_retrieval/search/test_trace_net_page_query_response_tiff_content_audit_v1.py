import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_page_query_response_tiff_content_audit_v1 import (
    AuditOptions,
    Thresholds,
    build_tiff_content_audit,
    check_quality,
    parse_vision_response,
)


def _make_zip(tmp_path: Path) -> Path:
    zp = tmp_path / "metadata.zip"
    blank = Image.new("1", (200, 300), 1)
    text = Image.new("1", (200, 300), 1)
    draw = ImageDraw.Draw(text)
    draw.text((20, 40), "PARTS LIST", fill=0)
    draw.rectangle((20, 80, 180, 220), outline=0)
    with zipfile.ZipFile(zp, "w") as z:
        for name, img in [("00000001.tif", text), ("00000002.tif", blank)]:
            p = tmp_path / name
            img.save(p)
            z.write(p, name)
        z.writestr("metadata.xml", "<mets></mets>")
    return zp


def _make_dataset(tmp_path: Path) -> Path:
    payload = {
        "quality_status": "PASS",
        "query_response_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "question": "Which parts-list information is on page 1?",
                "response": "Page t_p_120_1176_p000001 (00000001.tif) was resolved through the TRACE-Net graph/source package path. The source-linked page appears to contain a parts list. This is retrieval only.",
                "blank_expected": False,
                "source_identity": {"source_package_entry_name": "00000001.tif"},
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "question": "What is on page 2? If blank, say blank.",
                "response": "Page t_p_120_1176_p000002 (00000002.tif) was resolved through the TRACE-Net graph/source package path. The page is blank or empty, so there is no page content to summarize.",
                "blank_expected": True,
                "source_identity": {"source_package_entry_name": "00000002.tif"},
            },
        ],
    }
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_tiff_content_audit_heuristics_pass(tmp_path):
    dataset = _make_dataset(tmp_path)
    zp = _make_zip(tmp_path)
    options = AuditOptions(
        page_query_response_dataset=dataset,
        metadata_zip=zp,
        output_dir=tmp_path / "out",
        first_pages=2,
        thresholds=Thresholds(
            min_records=2,
            min_image_opened=2,
            min_blank_image_matches=1,
            min_response_page_anchors=2,
            min_response_source_entry_anchors=2,
            max_blank_mismatches=0,
            require_dataset_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    payload = build_tiff_content_audit(options)
    summary = payload["summary"]
    assert summary["record_count"] == 2
    assert summary["image_opened_count"] == 2
    assert summary["blank_image_response_match_count"] == 1
    assert summary["blank_mismatch_count"] == 0
    quality = check_quality(payload, options.thresholds)
    assert quality["quality_status"] == "PASS"


def test_build_tiff_content_audit_flags_blank_mismatch(tmp_path):
    dataset = _make_dataset(tmp_path)
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    payload["query_response_records"][0]["blank_expected"] = True
    payload["query_response_records"][0]["response"] = "Page t_p_120_1176_p000001 (00000001.tif) is blank."
    dataset.write_text(json.dumps(payload), encoding="utf-8")
    zp = _make_zip(tmp_path)
    options = AuditOptions(
        page_query_response_dataset=dataset,
        metadata_zip=zp,
        output_dir=tmp_path / "out",
        first_pages=2,
        thresholds=Thresholds(min_records=2, min_image_opened=2, max_blank_mismatches=0),
    )
    report = build_tiff_content_audit(options)
    assert report["summary"]["blank_mismatch_count"] >= 1
    quality = check_quality(report, options.thresholds)
    assert quality["quality_status"] == "FAIL"


def test_parse_vision_response_line_mode():
    parsed = parse_vision_response("VERDICT: PASS\nBLANK_PAGE: false\nIMAGE_SUMMARY: A table is visible.\nREASONS: table visible")
    assert parsed["verdict"] == "PASS"
    assert parsed["blank_page"] is False
    assert "table" in parsed["image_summary"].lower()
