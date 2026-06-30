from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_image_route_fast_chat_adapter_v1 import build_adapter, select_evidence
from tiff.trace_net_image_route_multi_route_quality_gate_v1 import evaluate_gate


def _write_pack(tmp_path: Path) -> Path:
    pack = {
        "status": "TRACE_NET_IMAGE_VISUAL_EVIDENCE_PACK_BUILT",
        "quality_status": "PASS",
        "records": [
            {
                "citation_label": "V6",
                "page_id": "t_p_120_1176_p000315",
                "page_number": 315,
                "figure": "69",
                "callout": "",
                "linked": True,
                "linked_part_number": "120-50645-005",
                "linked_description": "",
                "link_confidence": "MEDIUM",
                "proof_strength": "linked_visual_plus_figure_page_table_proof",
                "proof_source": "trusted_ocr_table_figure_item_evidence",
                "visual_source": "llava_ocr_visual_route",
                "source_trace_ready": True,
                "citation_ready": True,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "citation_label": "V99",
                "page_id": "t_p_120_1176_p000498",
                "page_number": 498,
                "figure": "608",
                "callout": "",
                "linked": False,
                "linked_part_number": "",
                "link_confidence": "LOW",
                "proof_source": "none_llava_only",
                "source_trace_ready": False,
                "citation_ready": False,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            },
        ],
        "summary": {
            "linked_visual_evidence_count": 1,
            "low_confidence_visual_candidate_count": 1,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(pack), encoding="utf-8")
    return path


def test_select_evidence_prefers_requested_linked_figure(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    pack = json.loads(pack_path.read_text())
    selected, figure, callout = select_evidence(pack["records"], "What does figure 69 show?")
    assert figure == "69"
    assert callout == ""
    assert len(selected) == 1
    assert selected[0]["linked_part_number"] == "120-50645-005"


def test_fast_chat_adapter_builds_webui_ready_visual_answer(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    result = build_adapter(
        image_visual_evidence_pack=pack_path,
        question="What does figure 69 show?",
        output_dir=tmp_path / "out",
        require_webui_answer_ready=True,
        min_citations=1,
        min_source_trace_ready_citations=1,
        max_unsupported_claims=0,
        max_llava_only_part_identity_claims=0,
        max_unsafe=0,
        max_answer_permission=0,
        max_source_truth_mutation_allowed=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["route_type"] == "image_or_diagram"
    assert result["webui_answer_ready"] is True
    assert "120-50645-005" in result["answer"]
    assert "does not prove interchangeability" in result["answer"]
    assert result["summary"]["llava_only_part_identity_claim_count"] == 0
    assert Path(result["paths"]["adapter"]).exists()


def test_fast_chat_adapter_keeps_unlinked_visual_candidate_review_only(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    result = build_adapter(
        image_visual_evidence_pack=pack_path,
        question="What does figure 608 show?",
        output_dir=tmp_path / "out",
        require_webui_answer_ready=False,
        min_citations=0,
        min_source_trace_ready_citations=0,
    )
    assert result["quality_status"] == "FAIL"  # no linked proof, so not answer-ready under safety contract
    assert result["webui_answer_ready"] is False
    assert "cannot identify a part number" in result["answer"]
    assert result["summary"]["llava_only_part_identity_claim_count"] == 0


def test_image_route_quality_gate_passes_good_adapter(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    adapter = build_adapter(
        image_visual_evidence_pack=pack_path,
        question="What does figure 69 show?",
        output_dir=tmp_path / "out",
        require_webui_answer_ready=True,
        min_citations=1,
        min_source_trace_ready_citations=1,
    )
    gate = evaluate_gate(
        adapter,
        require_webui_answer_ready=True,
        min_citations=1,
        min_source_trace_ready_citations=1,
        max_unsupported_claims=0,
        max_llava_only_part_identity_claims=0,
        max_unsafe=0,
        max_answer_permission=0,
        max_source_truth_mutation_allowed=0,
        max_write_attempts=0,
    )
    assert gate["quality_status"] == "PASS"
    assert gate["summary"]["image_route_quality_gate_ready"] is True


def test_image_route_quality_gate_rejects_llava_only_part_identity_claim() -> None:
    bad_adapter = {
        "status": "TRACE_NET_IMAGE_ROUTE_FAST_CHAT_ADAPTER_BUILT",
        "quality_status": "PASS",
        "route_type": "image_or_diagram",
        "webui_answer_ready": True,
        "answer": "Figure 1 shows part number 120-11111-001.",
        "citations": [],
        "summary": {
            "citation_count": 0,
            "source_trace_ready_citation_count": 0,
            "linked_citation_count": 0,
            "unsupported_claim_count": 0,
            "llava_only_part_identity_claim_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        },
    }
    gate = evaluate_gate(
        bad_adapter,
        require_webui_answer_ready=True,
        min_citations=1,
        min_source_trace_ready_citations=1,
        max_llava_only_part_identity_claims=0,
    )
    assert gate["quality_status"] == "FAIL"
    assert gate["summary"]["llava_only_part_identity_claim_count"] == 1
