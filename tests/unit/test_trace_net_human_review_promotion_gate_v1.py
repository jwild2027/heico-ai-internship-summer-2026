from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_human_review_promotion_gate_v1 import (
    APPROVED_STATUS,
    DENIED_STATUS,
    NON_PROMOTION_STATUS,
    build_promotion_gate_report,
    evaluate_promotion_decision,
    quality_report,
    write_json,
)


def decision(decision_type: str, **kwargs):
    base = {
        "review_decision_id": f"hrdec__{decision_type}",
        "decision_type": decision_type,
        "target_type": "triage_card",
        "target_id": "triage_card_1",
        "triage_card_id": "triage_card_1",
        "page_ids": ["page_1"],
        "citation_ids": [],
        "part_numbers": [],
        "promotion_candidate": decision_type in {"approve", "confirm_blank", "confirm_table_repair", "confirm_callout", "confirm_part_link"},
        "unsafe_decision": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    }
    base.update(kwargs)
    return base


def support_context():
    return {
        "repairs_by_page": {"page_1": [{"page_id": "page_1", "merged_part_number": "120-46137-001", "repair_status": "catalog_supported"}]},
        "repairs_by_part": {"120-46137-001": [{"page_id": "page_1", "merged_part_number": "120-46137-001", "repair_status": "catalog_supported"}]},
        "candidates_by_page": {"page_1": [{"page_id": "page_1", "rag_bucket": "source_text_evidence", "citation_id": "cite:page_1:abc"}]},
        "candidates_by_part": {"120-46137-001": [{"page_id": "page_1", "rag_bucket": "verified_part_evidence", "citation_id": "cite:part:abc"}]},
        "citation_ids": {"cite:page_1:abc", "cite:part:abc"},
        "graph_part_nodes": {"120-46137-001": {"part_number": "120-46137-001"}},
        "graph_page_ids": {"page_1"},
    }


def test_non_promotion_decision_is_not_promoted():
    record = evaluate_promotion_decision(decision("needs_more_review", promotion_candidate=False), triage_cards={}, support_context=support_context())
    assert record["promotion_gate_status"] == NON_PROMOTION_STATUS
    assert record["approved_for_controlled_promotion"] is False
    assert record["can_mutate_source_truth"] is False


def test_confirm_table_repair_with_catalog_and_citation_is_eligible():
    record = evaluate_promotion_decision(
        decision("confirm_table_repair", part_numbers=["120-46137-001"]),
        triage_cards={},
        support_context=support_context(),
    )
    assert record["promotion_gate_status"] == APPROVED_STATUS
    assert record["approved_for_controlled_promotion"] is True
    assert record["requires_writeback_gate"] is True
    assert record["approved_without_citation"] is False
    assert record["source_truth_mutation_allowed"] is False


def test_confirm_part_link_without_support_is_denied():
    record = evaluate_promotion_decision(
        decision("confirm_part_link", page_ids=[], part_numbers=["NO-SUCH-PART"]),
        triage_cards={},
        support_context=support_context(),
    )
    assert record["promotion_gate_status"] == DENIED_STATUS
    assert record["approved_for_controlled_promotion"] is False
    assert record["failed_check_count"] >= 1


def test_confirm_callout_requires_separate_visual_gate():
    record = evaluate_promotion_decision(decision("confirm_callout"), triage_cards={}, support_context=support_context())
    assert record["promotion_gate_status"] == "promotion_review_required"
    assert record["approved_for_controlled_promotion"] is False


def test_build_promotion_report_from_files(tmp_path: Path):
    decisions = {
        "quality_status": "PASS",
        "summary": {"status": "PASS"},
        "decision_records": [
            decision("needs_more_review", promotion_candidate=False),
            decision("confirm_table_repair", part_numbers=["120-46137-001"]),
        ],
    }
    triage = {"quality_status": "PASS", "triage_cards": [{"triage_card_id": "triage_card_1", "page_ids": ["page_1"], "part_numbers": ["120-46137-001"]}]}
    table = {"quality_status": "PASS", "records": [{"page_id": "page_1", "repairs": [{"merged_part_number": "120-46137-001", "repair_status": "catalog_supported"}]}]}
    embeds = {"quality_status": "PASS", "records": [{"page_id": "page_1", "rag_bucket": "source_text_evidence", "citation_id": "cite:page_1:abc", "source_candidate_id": "120-46137-001"}]}
    graph = {"quality_status": "PASS", "part_candidate_nodes": [{"part_number": "120-46137-001", "source_page_ids": ["page_1"]}]}
    decisions_path = tmp_path / "decisions.json"
    triage_path = tmp_path / "triage.json"
    table_path = tmp_path / "table.json"
    embeds_path = tmp_path / "embeds.json"
    graph_path = tmp_path / "graph.json"
    for path, payload in [(decisions_path, decisions), (triage_path, triage), (table_path, table), (embeds_path, embeds), (graph_path, graph)]:
        write_json(path, payload)
    report = build_promotion_gate_report(
        review_decisions_path=decisions_path,
        output_dir=tmp_path / "out",
        triage_report_path=triage_path,
        table_cell_normalizer_path=table_path,
        embedding_candidates_path=embeds_path,
        graph_overlay_part_normalizer_path=graph_path,
        min_review_decisions=2,
        min_promotion_evaluations=1,
        require_source_decision_quality_pass=True,
        require_source_triage_quality_pass=True,
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["promotion_candidate_count"] == 1
    assert report["summary"]["promotion_approved_count"] == 1
    assert (tmp_path / "out" / "trace_net_human_review_promotion_gate_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_human_review_promotion_gate_v1_quality.json").exists()


def test_quality_report_fails_on_unsafe_approval():
    records = [
        {
            "promotion_candidate": True,
            "promotion_gate_status": APPROVED_STATUS,
            "approved_without_citation": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
            "source_truth_mutations_performed": 0,
            "final_answer_allowed": False,
            "raw_feedback_direct_to_llm": False,
            "unsafe_promotion_record": True,
        }
    ]
    quality = quality_report(records, min_review_decisions=1, min_promotion_evaluations=1)
    assert quality["status"] == "FAIL"
