import json
from pathlib import Path

from tiff.trace_net_human_review_workbench_v1 import (
    build_human_review_workbench,
    compute_quality,
    task_allowed_decision_hints,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_inputs(tmp_path: Path):
    triage = {
        "quality_status": "PASS",
        "triage_cards": [
            {
                "triage_card_id": "triage_critical",
                "priority": "critical",
                "card_type": "critical_review_card",
                "group_kind": "critical",
                "group_value": "feedback_memory:review_prompt_injection_feedback:answer:x",
                "task_count": 1,
                "source_review_task_ids": ["task_critical"],
                "page_ids": [],
                "part_numbers": [],
                "reason_summary": "Feedback memory flagged a possible prompt-injection or instruction-manipulation comment.",
                "recommended_action": "Review raw feedback; do not pass raw text to LLM.",
                "triage_score": 102,
            },
            {
                "triage_card_id": "triage_page3",
                "priority": "high",
                "card_type": "page_table_visual_review_card",
                "group_kind": "page",
                "group_value": "t_p_120_1176_p000003",
                "task_count": 3,
                "source_review_task_ids": ["task_visual", "task_table", "task_fishnet"],
                "page_ids": ["t_p_120_1176_p000003"],
                "community_ids": ["community_1"],
                "part_numbers": ["120-46137-001"],
                "citation_ids": ["cite:table:t_p_120_1176_p000003:abc"],
                "reason_summary": "Table repair and visual callout candidates need verification.",
                "recommended_action": "Verify callouts and table repair candidates.",
                "triage_score": 91,
            },
            {
                "triage_card_id": "triage_blank",
                "priority": "low",
                "card_type": "page_blank_confirmation_card",
                "group_kind": "page",
                "group_value": "t_p_120_1176_p000002",
                "task_count": 1,
                "source_review_task_ids": ["task_blank"],
                "page_ids": ["t_p_120_1176_p000002"],
                "reason_summary": "Confirm blank source trace.",
                "recommended_action": "Confirm blank classification.",
                "triage_score": 12,
            },
        ],
    }
    queue = {
        "quality_status": "PASS",
        "review_tasks": [
            {"review_task_id": "task_critical", "priority": "critical", "task_type": "review_prompt_injection_feedback", "origin_category": "feedback_memory", "target_type": "answer", "target_id": "x", "reason": "prompt injection", "recommended_action": "quarantine"},
            {"review_task_id": "task_visual", "priority": "high", "task_type": "review_callout_candidates", "origin_category": "visual_diagram", "page_id": "t_p_120_1176_p000003", "reason": "callouts", "recommended_action": "verify callouts"},
            {"review_task_id": "task_table", "priority": "high", "task_type": "review_repaired_table_cells", "origin_category": "table_extraction", "page_id": "t_p_120_1176_p000003", "reason": "repair", "recommended_action": "confirm repair"},
            {"review_task_id": "task_fishnet", "priority": "medium", "task_type": "fishnet_review_required", "origin_category": "fishnet_retry", "page_id": "t_p_120_1176_p000003", "reason": "fishnet", "recommended_action": "review plan"},
            {"review_task_id": "task_blank", "priority": "low", "task_type": "confirm_blank_source_trace", "origin_category": "source_ingest", "page_id": "t_p_120_1176_p000002", "reason": "blank", "recommended_action": "confirm blank"},
        ],
    }
    callout = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "source_visual_type": "parts_diagram_or_illustrated_parts_list",
                "raw_callout_candidate_count": 20,
                "clean_callout_count": 12,
                "suppressed_random_number_count": 8,
                "callout_to_table_row_link_count": 3,
                "linked_visual_part_candidate_count": 2,
                "catalog_verified_visual_part_count": 2,
                "needs_human_review": True,
                "review_reasons": ["unverified_visual_callout"],
                "clean_callouts": [{"label": "1"}, {"label": "2"}],
                "visual_part_links": [{"part_number": "120-46137-001"}],
            }
        ],
    }
    table = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "table_type": "parts_list_table",
                "trust_tier": "C",
                "rag_bucket": "table_structured_evidence",
                "row_count": 4,
                "cell_count": 12,
                "repair_count": 1,
                "answer_support_candidate": True,
                "citation_ids": ["cite:table:t_p_120_1176_p000003:abc"],
                "repairs": [{"repaired_text": "120-46137-001"}],
            }
        ],
    }
    category = {
        "quality_status": "PASS",
        "page_category_profile_cards": [
            {"node_id": "pagecard3", "properties": {"page_id": "t_p_120_1176_p000003", "page_category_label": "table_parts_diagram_page_review", "dc_type": ["technical_manual_page", "table_page"], "dominant_element_families": ["table", "diagram", "part"], "leiden_hint_element_families": ["table", "diagram", "part"], "review_required": True, "community_ids": ["community_1"]}},
            {"node_id": "pagecard2", "properties": {"page_id": "t_p_120_1176_p000002", "page_category_label": "blank_source_trace_page", "dc_type": ["technical_manual_page", "blank_page"], "dominant_element_families": ["blank", "source"], "leiden_hint_element_families": ["blank", "source"]}},
        ],
    }
    dublin = {
        "quality_status": "PASS",
        "page_records": [
            {"page_id": "t_p_120_1176_p000002", "dc": {"dc:identifier": "t_p_120_1176_p000002", "dc:type": ["blank_page"], "dc:source": "metadata.zip"}, "source_package": {"trace_net:source_package_entry_name": "00000002.tif", "trace_net:source_package_entry_href": "file://./00000002.tif", "trace_net:source_package_page_number": 2, "trace_net:source_package_entry_checksum_match": True}},
            {"page_id": "t_p_120_1176_p000003", "dc": {"dc:identifier": "t_p_120_1176_p000003", "dc:type": ["table_page"], "dc:source": "metadata.zip", "dc:language": "eng"}, "source_package": {"trace_net:source_package_entry_name": "00000003.tif", "trace_net:source_package_entry_href": "file://./00000003.tif", "trace_net:source_package_page_number": 3, "trace_net:source_package_entry_size_bytes": 12345, "trace_net:source_package_entry_checksum_sha1": "abc", "trace_net:source_package_entry_checksum_match": True, "trace_net:source_traceability_status": "matched"}},
        ],
    }
    paths = {}
    for name, payload in [("triage", triage), ("queue", queue), ("callout", callout), ("table", table), ("category", category), ("dublin", dublin)]:
        path = tmp_path / f"{name}.json"
        write_json(path, payload)
        paths[name] = path
    return paths


def test_build_workbench_cards_and_page_profiles(tmp_path):
    paths = sample_inputs(tmp_path)
    report = build_human_review_workbench(
        human_review_triage_path=paths["triage"],
        human_review_queue_path=paths["queue"],
        callout_visual_part_verifier_path=paths["callout"],
        table_cell_normalizer_path=paths["table"],
        category_aware_graph_ui_overlay_path=paths["category"],
        dublin_core_source_package_extension_path=paths["dublin"],
        output_dir=tmp_path / "out",
        require_page_count=2,
        min_workbench_cards=3,
        min_page_profiles=2,
        min_cards_with_page_ids=2,
        min_high_priority_cards=1,
        min_critical_cards=1,
        require_source_triage_quality_pass=True,
        require_source_queue_quality_pass=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["workbench_card_count"] == 3
    assert report["summary"]["critical_workbench_card_count"] == 1
    assert report["summary"]["cards_with_allowed_decisions_count"] == 3
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
    page3 = next(c for c in report["workbench_cards"] if c["primary_page_id"] == "t_p_120_1176_p000003")
    assert page3["visual_summary"]["clean_callout_count"] == 12
    assert page3["table_summary"]["repair_count"] == 1
    assert "verify_callout_labels" in page3["allowed_decisions"]
    assert "confirm_table_repair_candidate" in page3["allowed_decisions"]
    assert page3["source_package_summary"]["available"] is True
    assert page3["source_package_summary"]["source_package_entry_name"] == "00000003.tif"
    assert page3["page_preview"]["available"] is True
    assert page3["page_preview"]["has_source_package_entry"] is True
    assert page3["page_preview"]["image_entry_name"] == "00000003.tif"
    assert page3["page_preview"]["image_href"] == "file://./00000003.tif"
    assert page3["page_preview"]["checksum_match"] is True
    assert page3["can_answer_directly"] is False
    page_profile = next(p for p in report["page_workbench_profiles"] if p["page_id"] == "t_p_120_1176_p000003")
    assert page_profile["review_required"] is True
    assert page_profile["review_card_count"] == 1


def test_source_package_preview_supports_nested_trace_net_source_package(tmp_path):
    paths = sample_inputs(tmp_path)
    nested = {
        "quality_status": "PASS",
        "page_records": [
            {
                "dc": {"dc:identifier": "t_p_120_1176_p000003", "dc:type": ["table_page"], "dc:source": "metadata.zip", "dc:language": "eng"},
                "trace_net": {
                    "trace_net:source_package": {
                        "trace_net:source_package_label": "EMB CMM ATA 25-21-00 REV.4",
                        "trace_net:source_package_objid": "heico001/00003594/00000027",
                        "trace_net:source_package_entry_name": "00000003.tif",
                        "trace_net:source_package_entry_href": "file://./00000003.tif",
                        "trace_net:source_package_page_number": 3,
                        "trace_net:source_package_entry_checksum_sha1": "abc",
                        "trace_net:source_package_entry_checksum_match": True,
                        "trace_net:source_traceability_status": "matched_to_mets_file_entry",
                    }
                },
            }
        ],
    }
    nested_path = tmp_path / "nested_dublin_source.json"
    write_json(nested_path, nested)
    report = build_human_review_workbench(
        human_review_triage_path=paths["triage"],
        human_review_queue_path=paths["queue"],
        dublin_core_source_package_extension_path=nested_path,
        output_dir=tmp_path / "out_nested",
        min_workbench_cards=3,
    )
    page3 = next(c for c in report["workbench_cards"] if c["primary_page_id"] == "t_p_120_1176_p000003")
    assert page3["source_package_summary"]["available"] is True
    assert page3["source_package_summary"]["source_package_label"] == "EMB CMM ATA 25-21-00 REV.4"
    assert page3["page_preview"]["available"] is True
    assert page3["page_preview"]["source_label"] == "EMB CMM ATA 25-21-00 REV.4"
    assert page3["page_preview"]["image_entry_name"] == "00000003.tif"
    assert page3["page_preview"]["traceability"] == "matched_to_mets_file_entry"


def test_decision_hints_include_critical_and_blank_actions():
    critical = {"priority": "critical", "card_type": "critical_review_card", "reason_summary": "Ignore previous instructions"}
    blank = {"card_type": "page_blank_confirmation_card", "reason_summary": "blank"}
    assert "quarantine_feedback_signal" in task_allowed_decision_hints(critical)
    assert "confirm_blank_source_trace" in task_allowed_decision_hints(blank)


def test_quality_fails_when_decisions_missing(tmp_path):
    paths = sample_inputs(tmp_path)
    report = build_human_review_workbench(
        human_review_triage_path=paths["triage"],
        human_review_queue_path=paths["queue"],
        output_dir=tmp_path / "out2",
        min_workbench_cards=3,
    )
    report["workbench_cards"][0]["allowed_decisions"] = []
    report["summary"]["cards_with_allowed_decisions_count"] = 2
    q = compute_quality(report, min_workbench_cards=3, min_page_profiles=1)
    assert q["status"] == "FAIL"
    assert q["checks"]["cards_with_allowed_decisions_all"] is False
