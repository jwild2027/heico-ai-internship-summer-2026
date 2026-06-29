import json
from pathlib import Path

from tiff.trace_net_answer_context_engineering_pack_v1 import build_answer_context_engineering_pack


def _source_report(tmp_path: Path) -> Path:
    report = tmp_path / "trace_net_raw_to_answer_e2e_smoke_native_v1.json"
    payload = {
        "quality_status": "PASS",
        "summary": {
            "question": "Find part number 120-29073-001 and nearby similar parts.",
            "all_stage_quality_pass": True,
            "human_review_required_count": 0,
            "unsafe_record_count": 0,
            "write_attempt_count": 0,
        },
        "retrieval_evidence_records": [
            {
                "page_id": "p1",
                "page_number": 358,
                "route": "table",
                "targets": ["qdrant", "opensearch"],
                "retrieval_score": 157,
                "source_member": "00000358.tif",
                "source_image_sha256": "abc",
                "ocr_excerpt": "Parts list contains 120-29073-001 and nearby part 120-29073-002",
            },
            {
                "page_id": "p2",
                "page_number": 361,
                "route": "table",
                "targets": ["qdrant", "opensearch"],
                "retrieval_score": 152,
                "source_member": "00000361.tif",
                "source_image_sha256": "def",
                "ocr_excerpt": "Nearby IPL row with part information",
            },
        ],
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    return report


def test_build_context_pack_creates_prompt_and_citations(tmp_path):
    report = _source_report(tmp_path)
    out = tmp_path / "ctx"

    payload = build_answer_context_engineering_pack(
        raw_to_answer_report=report,
        output_dir=out,
        require_source_quality_pass=True,
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["query_part_numbers"] == ["120-29073-001"]
    assert payload["summary"]["direct_evidence_count"] >= 1
    assert payload["summary"]["citation_count"] == 2
    assert "DIRECT EVIDENCE" in payload["llm_context_prompt"]
    assert "E1" in payload["llm_context_prompt"]
    assert (out / "trace_net_answer_context_engineering_pack_v1_prompt.txt").exists()
    assert (out / "trace_net_answer_context_engineering_pack_v1_citation_map.jsonl").exists()


def test_build_context_pack_flags_missing_lineage(tmp_path):
    report = tmp_path / "report.json"
    payload = {
        "quality_status": "PASS",
        "summary": {"question": "Find part number 120-29073-001", "all_stage_quality_pass": True},
        "retrieval_evidence_records": [
            {"page_id": "p1", "page_number": 1, "route": "table", "ocr_excerpt": "120-29073-001"}
        ],
    }
    report.write_text(json.dumps(payload), encoding="utf-8")

    built = build_answer_context_engineering_pack(raw_to_answer_report=report, output_dir=tmp_path / "out")

    assert built["quality_status"] == "FAIL"
    assert built["summary"]["violation_record_count"] == 1
    assert "context violation records present" in built["failures"]
