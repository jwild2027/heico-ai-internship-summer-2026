import json
from pathlib import Path

from tiff.trace_net_part_number_exact_retrieval_probe_v1 import build_part_number_exact_retrieval_probe


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_probe_finds_exact_part_in_trusted_ocr_text(tmp_path):
    ocr = _write(
        tmp_path / "ocr.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "p343",
                    "page_number": 343,
                    "source_member": "00000343.tif",
                    "ocr_text": "FIG ITEM PART NUMBER 1 | 120-29073-001 . STRUCTURE, LATERAL LEG VS4956 1",
                    "route": "table",
                },
                {"page_id": "p5", "page_number": 5, "source_member": "00000005.tif", "ocr_text": "LEP page"},
            ],
        },
    )
    payload = build_part_number_exact_retrieval_probe(
        question="Find part number 120-29073-001",
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["exact_direct_hit_count"] == 1
    assert payload["summary"]["direct_exact_page_numbers"] == [343]
    assert payload["direct_evidence_records"][0]["proof_role"] == "direct_exact_match_proven"


def test_probe_ignores_question_metadata_as_proof(tmp_path):
    ocr = _write(
        tmp_path / "ocr.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "p45",
                    "page_number": 45,
                    "question": "Find 120-29073-001",
                    "ocr_text": "120-40636-001 table content only",
                }
            ],
        },
    )
    payload = build_part_number_exact_retrieval_probe(
        question="Find part number 120-29073-001",
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
    )
    assert payload["summary"]["exact_hit_count"] == 0
    assert payload["summary"]["family_variant_hit_count"] == 0


def test_probe_classifies_part_number_list_as_reference_not_direct_proof(tmp_path):
    ocr = _write(
        tmp_path / "ocr.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "p32",
                    "page_number": 32,
                    "source_member": "00000032.tif",
                    "extracted_part_numbers": ["120-29073-001", "120-29073-005"],
                    "ocr_text": "List of effective pages",
                }
            ],
        },
    )
    payload = build_part_number_exact_retrieval_probe(
        question="Find part number 120-29073-001",
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
    )
    assert payload["summary"]["exact_hit_count"] == 1
    assert payload["summary"]["exact_direct_hit_count"] == 0
    assert payload["summary"]["exact_reference_hit_count"] == 1
    assert payload["reference_hit_records"][0]["proof_role"] == "exact_reference_candidate"


def test_probe_detects_family_variants(tmp_path):
    ocr = _write(
        tmp_path / "ocr.json",
        {
            "quality_status": "PASS",
            "records": [
                {"page_id": "p361", "page_number": 361, "ocr_text": "120-29073-005 and 120-29073-007 lateral leg variants"}
            ],
        },
    )
    payload = build_part_number_exact_retrieval_probe(
        question="Find part number 120-29073-001",
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
    )
    assert payload["summary"]["exact_hit_count"] == 0
    assert payload["summary"]["family_variant_hit_count"] >= 1
