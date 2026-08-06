import json
from pathlib import Path

from tiff.trace_net_dublin_core_crosswalk_refinement_v1 import build_refinement_report, quality_report


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def crosswalk_payload() -> dict:
    return {
        "schema_version": "trace_net_dublin_core_crosswalk_v1",
        "status": "DUBLIN_CORE_CROSSWALK_BUILT",
        "quality_status": "PASS",
        "page_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "dc": {
                    "dc:identifier": "t_p_120_1176_p000001",
                    "dc:type": ["technical_manual_page", "text_page", "table_page", "visual_page", "parts_page", "context_v2_page"],
                    "dc:source": "source_trace:t_p_120_1176_p000001",
                    "dc:format": "image/tiff",
                },
                "trace_net": {
                    "trace_net:element_type_counts": {
                        "source_trace": 1,
                        "source_text": 1,
                        "citation": 1,
                        "fishnet_plan": 1,
                        "fishnet_action": 6,
                        "community": 2,
                        "context_v2": 1,
                    },
                    "trace_net:review_required": False,
                    "trace_net:ocr_present": True,
                    "trace_net:context_v2_present": True,
                    "trace_net:community_ids": ["tracenet_community_00001"],
                },
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "dc": {
                    "dc:identifier": "t_p_120_1176_p000002",
                    "dc:type": ["technical_manual_page", "blank_page", "text_page", "table_page", "visual_page"],
                    "dc:source": "source_trace:t_p_120_1176_p000002",
                    "dc:format": "image/tiff",
                },
                "trace_net": {
                    "trace_net:element_type_counts": {
                        "blank_source_trace_preservation": 1,
                        "source_trace": 1,
                        "citation": 1,
                        "fishnet_plan": 1,
                        "fishnet_action": 4,
                        "community": 1,
                        "layout:blank": 1,
                    },
                    "trace_net:source_confirmed_blank": True,
                    "trace_net:review_required": False,
                },
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "dc": {
                    "dc:identifier": "t_p_120_1176_p000003",
                    "dc:type": ["technical_manual_page", "text_page", "table_page", "visual_page", "parts_page"],
                    "dc:source": "source_trace:t_p_120_1176_p000003",
                    "dc:format": "image/tiff",
                },
                "trace_net": {
                    "trace_net:element_type_counts": {
                        "source_trace": 1,
                        "source_text": 1,
                        "table": 1,
                        "table_row": 75,
                        "table_cell": 140,
                        "table_repair": 2,
                        "visual_region": 1,
                        "callout_candidate": 12,
                        "linked_part_candidate": 10,
                        "fishnet_plan": 1,
                        "fishnet_action": 12,
                        "review_task": 4,
                        "community": 3,
                    },
                    "trace_net:review_required": True,
                    "trace_net:review_task_ids": ["triage_1"],
                    "trace_net:community_ids": ["tracenet_community_00002"],
                },
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
        ],
        "document_records": [{"document_id": "t_p_120_1176", "dc": {"dc:identifier": "t_p_120_1176"}, "trace_net": {}}],
    }


def test_refinement_splits_physical_and_operational_counts(tmp_path: Path) -> None:
    source = tmp_path / "crosswalk.json"
    write_json(source, crosswalk_payload())
    report = build_refinement_report(
        crosswalk_path=source,
        output_dir=tmp_path / "out",
        quality_config={
            "require_page_count": 3,
            "min_records_with_physical_counts": 3,
            "min_records_with_operational_counts": 3,
            "min_records_with_review_summary": 3,
            "min_blank_pages_with_low_physical": 1,
            "max_clean_overbroad_dc_type": 0,
        },
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["page_record_count"] == 3
    assert report["summary"]["old_overbroad_dc_type_count"] >= 2
    assert report["summary"]["clean_overbroad_dc_type_count"] == 0
    page1 = next(r for r in report["page_records"] if r["page_id"] == "t_p_120_1176_p000001")
    assert "text_page" in page1["dc"]["dc:type"]
    assert "table_page" not in page1["dc"]["dc:type"]
    assert "visual_page" not in page1["dc"]["dc:type"]
    assert "old_type:table_page" in page1["trace_net"]["trace_net:secondary_type_signals"]
    assert "old_type:visual_page" in page1["trace_net"]["trace_net:secondary_type_signals"]

    page2 = next(r for r in report["page_records"] if r["page_id"] == "t_p_120_1176_p000002")
    assert page2["dc"]["dc:type"] == ["blank_page", "technical_manual_page"]
    assert page2["trace_net"]["trace_net:physical_element_count"] <= 1
    assert page2["trace_net"]["trace_net:operational_element_count"] > 0
    page3 = next(r for r in report["page_records"] if r["page_id"] == "t_p_120_1176_p000003")
    assert "table_page" in page3["dc"]["dc:type"]
    assert "visual_page" in page3["dc"]["dc:type"]
    assert page3["trace_net"]["trace_net:physical_element_type_counts"]["table_cell"] == 140
    assert page3["trace_net"]["trace_net:operational_element_type_counts"]["fishnet_action"] == 12
    assert page3["trace_net"]["trace_net:review"]["review_required"] is True
    assert (tmp_path / "out" / "trace_net_dublin_core_refined_pages_v1.jsonl").exists()


def test_quality_report_fails_for_answer_permission(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    write_json(
        report_path,
        {
            "summary": {
                "page_record_count": 1,
                "records_with_physical_element_counts": 1,
                "records_with_operational_element_counts": 1,
                "records_with_review_summary": 1,
                "missing_clean_dc_type_count": 0,
                "direct_answer_allowed_count": 1,
                "claim_proof_allowed_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
            }
        },
    )
    quality = quality_report(report_path=report_path, quality_config={"require_page_count": 1})
    assert quality["status"] == "FAIL"


def test_document_refinement_summarizes_counts(tmp_path: Path) -> None:
    source = tmp_path / "crosswalk.json"
    write_json(source, crosswalk_payload())
    report = build_refinement_report(crosswalk_path=source, output_dir=tmp_path / "out")
    doc = report["document_records"][0]
    assert doc["trace_net"]["trace_net:physical_element_count"] > 0
    assert doc["trace_net"]["trace_net:operational_element_count"] > 0
    assert doc["can_answer_directly"] is False
