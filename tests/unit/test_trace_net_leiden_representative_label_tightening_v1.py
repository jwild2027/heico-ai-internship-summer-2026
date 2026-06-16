import json
from pathlib import Path

from tiff.trace_net_leiden_representative_label_tightening_v1 import (
    build_report,
    normalize_category_counts,
    macro_category,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_macro_category_normalizes_noisy_categories():
    assert macro_category("visual_evidence") == "visual_evidence"
    assert macro_category("opensearch:page_retrieval_profile") == "helper"
    assert macro_category("table_cell_normalized") == "table_evidence"
    assert macro_category("HAS_NOMENCLATURE_part") == "part_evidence"


def test_normalize_category_counts_collapses_to_macro_families():
    counts = normalize_category_counts(
        {
            "visual_evidence": 10,
            "diagram_region": 2,
            "table_cell_normalized": 4,
            "opensearch:page_retrieval_profile": 9,
            "fishnet_action": 3,
        }
    )
    assert counts["visual_evidence"] == 12
    assert counts["table_evidence"] == 4
    assert counts["helper"] == 9
    assert counts["routing"] == 3


def test_build_report_refines_labels_and_representatives(tmp_path: Path):
    hydrator = _write(
        tmp_path / "hydrator.json",
        {
            "quality_status": "PASS",
            "community_hydration_records": [
                {
                    "community_id": "tracenet_community_00011",
                    "label": "Part family community 120-46137",
                    "page_count": 2,
                    "sample_page_ids": ["t_p_120_1176_p000003", "t_p_120_1176_p000340"],
                    "sample_part_numbers": ["120-46137-001", "120-46137-501"],
                    "category_counts": {
                        "table_evidence": 50,
                        "visual_evidence": 20,
                        "community_navigation": 100,
                        "opensearch:page_retrieval_profile": 10,
                    },
                },
                {
                    "community_id": "tracenet_community_00134",
                    "label": "Visual evidence community (1 page(s))",
                    "page_count": 1,
                    "sample_page_ids": ["t_p_120_1176_p000017"],
                    "category_counts": {"visual_evidence": 25, "text_source_page": 3},
                },
                {
                    "community_id": "tracenet_community_00229",
                    "label": "TRACE-Net graph community",
                    "page_count": 0,
                    "sample_page_ids": [],
                    "category_counts": {},
                },
            ],
        },
    )
    dublin = _write(
        tmp_path / "dublin.json",
        {
            "quality_status": "PASS",
            "page_records": [
                {"page_id": "t_p_120_1176_p000003", "page_number": 3, "dc": {"dc:type": ["technical_manual_page", "text_page"]}},
                {"page_id": "t_p_120_1176_p000340", "page_number": 340, "dc": {"dc:type": ["technical_manual_page"]}},
                {"page_id": "t_p_120_1176_p000017", "page_number": 17, "dc": {"dc:type": ["technical_manual_page"]}},
            ],
        },
    )

    report = build_report(
        leiden_category_summary_hydrator=hydrator,
        dublin_core_refined=dublin,
        output_dir=tmp_path / "out",
        thresholds={
            "min_communities": 3,
            "min_refined_labels": 3,
            "min_communities_with_representative_pages": 2,
            "max_missing_page_membership": 1,
            "max_missing_category_summary": 1,
            "require_hydrator_quality_pass": True,
            "require_dublin_core_quality_pass": True,
        },
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["community_profile_record_count"] == 3
    assert summary["communities_with_representative_pages_count"] == 2
    assert summary["missing_page_membership_count"] == 1
    assert summary["community_as_proof_count"] == 0

    records = report["community_profile_records"]
    part = records[0]
    assert part["refined_label"] == "Part family community 120-46137"
    assert part["representative_page_ids"] == ["t_p_120_1176_p000003", "t_p_120_1176_p000340"]
    assert part["navigation_intent"] == "part_family_navigation"
    assert part["can_answer_directly"] is False
    assert part["can_prove_claims"] is False


def test_build_report_fails_quality_when_threshold_is_too_strict(tmp_path: Path):
    hydrator = _write(
        tmp_path / "hydrator.json",
        {
            "quality_status": "PASS",
            "community_hydration_records": [
                {"community_id": "c1", "label": "TRACE-Net graph community", "page_count": 0, "category_counts": {}},
            ],
        },
    )
    dublin = _write(tmp_path / "dublin.json", {"quality_status": "PASS", "page_records": []})
    report = build_report(
        leiden_category_summary_hydrator=hydrator,
        dublin_core_refined=dublin,
        output_dir=tmp_path / "out",
        thresholds={"min_communities": 2},
    )
    assert report["quality_status"] == "FAIL"
    assert report["quality_failures"]
