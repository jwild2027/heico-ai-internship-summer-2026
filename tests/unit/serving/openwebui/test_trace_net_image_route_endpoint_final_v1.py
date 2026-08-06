from pathlib import Path
import json

from tiff.trace_net_image_route_openwebui_endpoint_v1 import build_endpoint_smoke, check_endpoint_smoke


def _pack(tmp_path: Path) -> Path:
    p = tmp_path / "pack.json"
    p.write_text(json.dumps({
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
                "source_trace_ready": True,
                "citation_ready": True,
                "proof_source": "trusted_ocr_table_figure_item_evidence",
                "visual_source": "llava_plus_ocr_extractor",
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "unsafe_record": False,
            }
        ],
        "summary": {
            "visual_evidence_record_count": 1,
            "linked_visual_evidence_count": 1,
            "source_trace_ready_count": 1,
            "citation_ready_count": 1,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "unsafe_record_count": 0,
            "write_attempt_count": 0,
        },
    }), encoding="utf-8")
    return p


def test_endpoint_smoke_builds_pass_direct_from_pack(tmp_path):
    manifest = build_endpoint_smoke(
        question="What does figure 69 show?",
        repo_root=Path.cwd(),
        context_pack=tmp_path / "context.json",
        image_visual_evidence_pack=_pack(tmp_path),
        output_dir=tmp_path / "smoke",
        require_quality_pass=True,
        require_webui_answer_ready=True,
        min_valid_citations=1,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["query_type"] == "image_or_diagram"
    assert manifest["query_route"] == "fast_image_diagram_answer"
    assert manifest["webui_answer_ready"] is True
    assert manifest["valid_answer_citation_count"] == 1
    assert "120-50645-005" in manifest["answer"]
    runner_report = tmp_path / "smoke"
    reports = list(runner_report.rglob("trace_net_fast_chat_runner_v1.json"))
    assert reports


def test_endpoint_smoke_check_passes(tmp_path):
    build_endpoint_smoke(
        question="What does figure 69 show?",
        repo_root=Path.cwd(),
        context_pack=tmp_path / "context.json",
        image_visual_evidence_pack=_pack(tmp_path),
        output_dir=tmp_path / "smoke",
        require_quality_pass=True,
        require_webui_answer_ready=True,
        min_valid_citations=1,
    )
    result = check_endpoint_smoke(
        manifest=tmp_path / "smoke" / "trace_net_image_route_openwebui_endpoint_smoke_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        require_webui_answer_ready=True,
        min_valid_citations=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["failure_count"] == 0
