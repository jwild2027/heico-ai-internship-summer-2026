from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_human_review_workbench_preview_wiring_v1 import (
    build_preview_wiring,
    index_source_pages,
    preview_for_page,
    source_package_block_for_page,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_workbench() -> dict:
    return {
        "quality_status": "PASS",
        "summary": {"workbench_card_count": 2},
        "workbench_cards": [
            {
                "workbench_card_id": "hrwb_page3",
                "triage_card_id": "triage_page3",
                "priority": "high",
                "card_type": "page_table_visual_review_card",
                "primary_page_id": "t_p_120_1176_p000003",
                "page_ids": ["t_p_120_1176_p000003"],
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "workbench_card_id": "hrwb_critical",
                "triage_card_id": "triage_critical",
                "priority": "critical",
                "card_type": "critical_review_card",
                "primary_page_id": None,
                "page_ids": [],
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
        ],
        "page_workbench_profiles": [
            {"page_workbench_profile_id": "profile3", "page_id": "t_p_120_1176_p000003"},
            {"page_workbench_profile_id": "profile4", "page_id": "t_p_120_1176_p000004"},
        ],
    }


def sample_source_extension() -> dict:
    return {
        "quality_status": "PASS",
        "summary": {
            "metadata_xml_present": True,
            "source_package_label": "EMB CMM ATA 25-21-00 REV.4",
            "source_package_objid": "heico001/00003594/00000027",
            "source_package_type": "ResCarta Monograph Metadata v3.1",
            "source_package_language_code": "eng",
            "source_package_tiff_count": 509,
            "source_package_entry_count": 510,
        },
        "page_records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "dc": {
                    "dc:identifier": "t_p_120_1176_p000003",
                    "dc:type": ["technical_manual_page", "table_page"],
                    "dc:source": "source_trace:t_p_120_1176_p000003",
                    "dc:language": "eng",
                },
                "source_package": {
                    "trace_net:source_package_id": "heico001/00003594/00000027",
                    "trace_net:source_package_label": "EMB CMM ATA 25-21-00 REV.4",
                    "trace_net:source_package_objid": "heico001/00003594/00000027",
                    "trace_net:source_package_type": "ResCarta Monograph Metadata v3.1",
                    "trace_net:source_package_entry_name": "00000003.tif",
                    "trace_net:source_package_entry_suffix": ".tif",
                    "trace_net:source_package_entry_href": "file://./00000003.tif",
                    "trace_net:source_package_page_number": 3,
                    "trace_net:source_package_entry_size_bytes": 70153,
                    "trace_net:source_package_entry_checksum_sha1": "abc123",
                    "trace_net:source_package_entry_checksum_match": True,
                    "trace_net:source_traceability_status": "matched_to_mets_file_entry",
                },
            },
            {
                "page_id": "t_p_120_1176_p000004",
                "dc": {"dc:identifier": "t_p_120_1176_p000004"},
                "source_package": {
                    "trace_net:source_package_entry_name": "00000004.tif",
                    "trace_net:source_package_entry_href": "file://./00000004.tif",
                    "trace_net:source_package_page_number": 4,
                    "trace_net:source_package_entry_checksum_match": True,
                },
            },
        ],
    }


def test_index_source_pages_supports_top_level_page_id() -> None:
    index = index_source_pages(sample_source_extension())
    assert set(index) == {"t_p_120_1176_p000003", "t_p_120_1176_p000004"}


def test_source_package_block_and_preview_are_available() -> None:
    src = sample_source_extension()
    index = index_source_pages(src)
    summary = source_package_block_for_page(index["t_p_120_1176_p000003"], {"metadata_xml_present": True})
    preview = preview_for_page("t_p_120_1176_p000003", summary)
    assert summary["available"] is True
    assert summary["source_package_entry_name"] == "00000003.tif"
    assert preview["available"] is True
    assert preview["has_source_package_entry"] is True
    assert preview["image_href"] == "file://./00000003.tif"
    assert preview["checksum_match"] is True


def test_build_preview_wiring_enriches_page_scoped_cards(tmp_path: Path) -> None:
    workbench_path = tmp_path / "workbench.json"
    source_path = tmp_path / "source.json"
    out = tmp_path / "out"
    write_json(workbench_path, sample_workbench())
    write_json(source_path, sample_source_extension())

    report = build_preview_wiring(
        human_review_workbench_path=workbench_path,
        dublin_core_source_package_extension_path=source_path,
        output_dir=out,
        min_workbench_cards=2,
        min_page_profiles=2,
        min_page_scoped_cards=1,
        min_cards_with_page_preview=1,
        min_cards_with_source_package_summary=1,
        min_page_profiles_with_preview=2,
        require_source_workbench_quality_pass=True,
        require_source_package_quality_pass=True,
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["workbench_card_count"] == 2
    assert report["summary"]["page_scoped_workbench_card_count"] == 1
    assert report["summary"]["cards_with_page_preview_count"] == 1
    assert report["summary"]["cards_with_source_package_summary_count"] == 1
    assert report["summary"]["missing_page_preview_for_page_scoped_card_count"] == 0

    page_card = next(c for c in report["workbench_cards"] if c["primary_page_id"])
    assert page_card["source_package_summary"]["available"] is True
    assert page_card["page_preview"]["image_entry_name"] == "00000003.tif"
    assert page_card["page_preview"]["page_number"] == 3
    assert page_card["can_answer_directly"] is False
    assert page_card["can_prove_claims"] is False
    assert page_card["source_truth_mutation_allowed"] is False

    critical = next(c for c in report["workbench_cards"] if not c["primary_page_id"])
    assert critical["source_package_summary"]["available"] is False
    assert critical["page_preview"]["available"] is False

    assert (out / "trace_net_human_review_workbench_preview_wiring_v1.json").exists()
    assert (out / "trace_net_human_review_workbench_preview_wiring_v1_cards.jsonl").exists()
    assert (out / "trace_net_human_review_workbench_preview_wiring_v1_quality.json").exists()
