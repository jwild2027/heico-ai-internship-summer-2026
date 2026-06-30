
import json
from pathlib import Path

from tiff.trace_net_image_visual_evidence_nomenclature_merger_v1 import build_merger, check_merger, _clean_nomenclature


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _pack(tmp_path):
    return _write(tmp_path / "pack.json", {
        "quality_status": "PASS",
        "records": [
            {
                "citation_label": "V6", "linked": True, "figure": "69", "page_id": "p315", "page_number": 315,
                "linked_part_number": "120-50645-005", "linked_description": "", "linked_description_quality": "missing_not_filename",
                "limitations": ["The visual link identifies the part number, but a clean nomenclature/description is not available in this record."],
                "source_trace_ready": True, "answer_permission": False, "source_truth_mutation_allowed": False,
            },
            {
                "citation_label": "V1", "linked": False, "figure": "1", "linked_part_number": "", "source_trace_ready": False,
                "answer_permission": False, "source_truth_mutation_allowed": False,
            }
        ]
    })


def _extractor(tmp_path):
    return _write(tmp_path / "extractor.json", {
        "quality_status": "PASS",
        "records": [
            {
                "source_visual_citation_label": "V6", "figure": "69", "linked_part_number": "120-50645-005",
                "selected_nomenclature": "DOUBLE PASSENGER SEAT ASSY", "selected_nomenclature_confidence": "HIGH",
                "selected_ocr_page_id": "p316", "selected_ocr_page_number": 316,
                "selected_line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF",
                "selected_extraction_rule": "same_line_after_part", "source_trace_ready": True,
                "answer_permission": False, "source_truth_mutation_allowed": False, "unsafe": False,
            }
        ]
    })


def test_clean_nomenclature_removes_ocr_noise():
    assert _clean_nomenclature("STRUCTURE ASSY 00") == "STRUCTURE ASSY"


def test_merger_updates_linked_description_and_limitations(tmp_path):
    artifact = build_merger(
        image_visual_evidence_pack=_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_extractor(tmp_path),
        output_dir=tmp_path / "out",
        min_visual_records=1,
        min_nomenclature_merged=1,
        min_source_trace_ready=1,
    )
    assert artifact["quality_status"] == "PASS"
    assert artifact["summary"]["nomenclature_merged_count"] == 1
    merged = json.loads((tmp_path / "out" / "trace_net_image_visual_evidence_pack_with_nomenclature_v1.json").read_text())
    rec = merged["records"][0]
    assert rec["linked_description"] == "DOUBLE PASSENGER SEAT ASSY"
    assert rec["linked_description_quality"] == "ocr_backed_high_confidence"
    assert "clean nomenclature/description is not available" not in " ".join(rec["limitations"])


def test_check_merger_passes(tmp_path):
    artifact = build_merger(_pack(tmp_path), _extractor(tmp_path), tmp_path / "out", min_nomenclature_merged=1, min_source_trace_ready=1)
    result = check_merger(tmp_path / "out" / "trace_net_image_visual_evidence_nomenclature_merger_v1.json", tmp_path / "check.json", require_quality_pass=True, min_nomenclature_merged=1, min_source_trace_ready=1)
    assert result["quality_status"] == "PASS"


def test_rejects_extractor_record_with_answer_permission(tmp_path):
    ext = json.loads(_extractor(tmp_path).read_text())
    ext["records"][0]["answer_permission"] = True
    ext_path = _write(tmp_path / "bad_extractor.json", ext)
    artifact = build_merger(_pack(tmp_path), ext_path, tmp_path / "out_bad", min_nomenclature_merged=0, min_source_trace_ready=0)
    assert artifact["quality_status"] == "PASS"
    assert artifact["summary"]["nomenclature_merged_count"] == 0
