import json
from pathlib import Path

from tiff.trace_net_raw_ocr_nomenclature_window_extractor_v1 import (
    build_extractor,
    check_extractor,
    _extract_after_part,
    _extract_title_parenthetical,
    _is_bad_nomenclature,
)


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_extract_same_line_nomenclature():
    line = "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF"
    assert _extract_after_part(line, "120-50645-005") == "DOUBLE PASSENGER SEAT ASSY"


def test_extract_parenthetical_title():
    line = "Double Passenger Seat Structure (120-29068-003)"
    assert _extract_title_parenthetical(line, "120-29068-003") == "Double Passenger Seat Structure"


def test_rejects_bad_values():
    assert _is_bad_nomenclature("120-50645-005", "120-50645-005")
    assert _is_bad_nomenclature("TRACE-Net page 315")
    assert _is_bad_nomenclature("Part family community 120-50645")
    assert not _is_bad_nomenclature("DOUBLE PASSENGER SEAT ASSY")


def test_build_extractor_selects_ocr_nomenclature(tmp_path):
    image_pack = _write(tmp_path / "image.json", {
        "quality_status": "PASS",
        "records": [
            {"citation_label": "V6", "evidence_id": "ev6", "linked": True, "linked_part_number": "120-50645-005", "figure": "69", "page_id": "p315", "page_number": 315, "source_trace_ready": True},
            {"citation_label": "V8", "evidence_id": "ev8", "linked": True, "linked_part_number": "120-29068-003", "figure": "91", "page_id": "p384", "page_number": 384, "source_trace_ready": True},
        ],
    })
    ocr = _write(tmp_path / "ocr.json", {
        "records": [
            {"page_id": "p316", "canonical_page_number": 316, "file_name": "00000316.tif", "ocr_sample_text": "FIG. ITEM PARTNUMBER\n69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF"},
            {"page_id": "p385", "canonical_page_number": 385, "file_name": "00000385.tif", "ocr_sample_text": "Double Passenger Seat Structure (120-29068-003)\nFigure 91"},
        ],
    })
    result = build_extractor(
        image_visual_evidence_pack=image_pack,
        ocr_route_scan_pack=[ocr],
        output_dir=tmp_path / "out",
        min_linked_visual_parts=2,
        min_nomenclature_selected=2,
        min_source_trace_ready=2,
    )
    assert result["quality_status"] == "PASS"
    names = {r["linked_part_number"]: r["selected_nomenclature"] for r in result["records"]}
    assert names["120-50645-005"] == "DOUBLE PASSENGER SEAT ASSY"
    assert names["120-29068-003"] == "Double Passenger Seat Structure"
    assert result["summary"]["answer_permission_count"] == 0


def test_check_extractor(tmp_path):
    extractor = _write(tmp_path / "extractor.json", {
        "quality_status": "PASS",
        "summary": {
            "linked_visual_part_count": 3,
            "nomenclature_selected_count": 3,
            "source_trace_ready_count": 3,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        },
    })
    result = check_extractor(
        extractor=extractor,
        output=tmp_path / "check.json",
        require_quality_pass=True,
        min_linked_visual_parts=1,
        min_nomenclature_selected=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
