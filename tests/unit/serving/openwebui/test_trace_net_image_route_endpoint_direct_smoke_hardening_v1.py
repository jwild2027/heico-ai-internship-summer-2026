import json
from pathlib import Path

from tiff.trace_net_image_route_openwebui_endpoint_v1 import build_endpoint_smoke, run_fast_chat_runner


def _write_pack(tmp_path: Path) -> Path:
    pack = {
        "status": "TRACE_NET_IMAGE_VISUAL_EVIDENCE_PACK_BUILT",
        "quality_status": "PASS",
        "records": [
            {
                "citation_label": "V1",
                "page_id": "p1",
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
            }
        ],
        "summary": {"linked_visual_evidence_count": 1},
    }
    p = tmp_path / "pack.json"
    p.write_text(json.dumps(pack), encoding="utf-8")
    return p


def test_run_fast_chat_runner_direct_path_returns_pass(tmp_path):
    pack = _write_pack(tmp_path)
    result = run_fast_chat_runner(
        question="What does figure 69 show?",
        repo_root=Path.cwd(),
        context_pack=tmp_path / "context.json",
        image_visual_evidence_pack=pack,
        output_root=tmp_path / "out",
    )
    assert result["quality_status"] == "PASS"
    summary = result["summary"]
    assert summary["query_type"] == "image_or_diagram"
    assert summary["webui_answer_ready"] is True
    assert summary["valid_answer_citation_count"] == 1
    assert result["report_found"] is True


def test_build_endpoint_smoke_direct_path_returns_pass(tmp_path):
    pack = _write_pack(tmp_path)
    manifest = build_endpoint_smoke(
        question="What does figure 69 show?",
        repo_root=Path.cwd(),
        context_pack=tmp_path / "context.json",
        image_visual_evidence_pack=pack,
        output_dir=tmp_path / "smoke",
        require_quality_pass=True,
        require_webui_answer_ready=True,
        min_valid_citations=1,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["query_route"] == "fast_image_diagram_answer"
    assert manifest["summary"]["valid_answer_citation_count"] == 1
    assert "120-50645-005" in manifest["answer"]
