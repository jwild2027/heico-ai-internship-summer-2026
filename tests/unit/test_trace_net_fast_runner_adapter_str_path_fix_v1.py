import json

from tiff.trace_net_image_route_fast_chat_adapter_v1 import build_adapter


def _pack():
    return {
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
            }
        ],
    }


def test_build_adapter_accepts_path_values(tmp_path):
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(_pack()), encoding="utf-8")
    out_dir = tmp_path / "out_path"
    result = build_adapter(
        image_visual_evidence_pack=pack_path,
        question="What does figure 69 show?",
        output_dir=out_dir,
        require_webui_answer_ready=True,
        min_citations=1,
        min_source_trace_ready_citations=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["webui_answer_ready"] is True
    assert (out_dir / "trace_net_image_route_fast_chat_adapter_v1.json").exists()


def test_build_adapter_accepts_string_paths_like_fast_chat_runner(tmp_path):
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(_pack()), encoding="utf-8")
    out_dir = tmp_path / "out_str"
    result = build_adapter(
        image_visual_evidence_pack=str(pack_path),
        question="What does figure 69 show?",
        output_dir=str(out_dir),
        require_webui_answer_ready=True,
        min_citations=1,
        min_source_trace_ready_citations=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["webui_answer_ready"] is True
    assert (out_dir / "trace_net_image_route_fast_chat_adapter_v1.json").exists()
