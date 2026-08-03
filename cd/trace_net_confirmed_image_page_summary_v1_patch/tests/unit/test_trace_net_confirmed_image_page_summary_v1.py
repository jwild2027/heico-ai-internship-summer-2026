from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path("scripts/build/visual/build_trace_net_confirmed_image_page_summary_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("confirmed_image_summary", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["confirmed_image_summary"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_clean_figure_refs_moves_dict_like_strings_to_metadata() -> None:
    mod = load_module()

    refs, metadata = mod.clean_figure_refs([
        "{'type': 'diagram', 'description': 'A technical drawing or schematic showing the assembly.'}",
        "609",
        "figure 609",
        "figure 26 sheet 1",
    ])

    assert "figure 609" in refs
    assert "figure 26 sheet 1" in refs
    assert "609" in refs
    assert metadata
    assert "technical drawing" in metadata[0]["description"].lower()


def test_build_summary_card_is_visual_guidance_only() -> None:
    mod = load_module()
    doc = {
        "document_id": "doc::p001",
        "page_id": "t_p_120_1176_p000001",
        "visual_route": "image_visual",
        "visual_subtype": "confirmed_diagram_dominant",
        "summary": "parts_diagram_or_illustrated_parts_list",
        "figure_refs": ["figure 2 sheet 1"],
        "part_numbers": ["120-41824-003"],
        "callouts": ["1", "25", "210", "{'type': 'diagram', 'description': 'metadata'}"],
    }

    card = mod.build_summary_card(
        doc,
        llava_observation=None,
        call_ollama_llava=False,
        call_ollama_gemma=False,
        image_roots=[],
        ollama_base_url="http://127.0.0.1:11434",
        llava_model="llava:13b",
        gemma_model="gemma4:26b",
        ollama_timeout_seconds=1.0,
    )

    assert card["page_id"] == "t_p_120_1176_p000001"
    assert card["visual_page_summary"]["visual_page_type"] == "illustrated_parts_list_or_parts_diagram"
    assert card["visual_page_summary"]["figure_refs_clean"] == ["figure 2 sheet 1"]
    assert card["safety_contract"]["answer_permission"] is False
    assert card["safety_contract"]["final_answer_allowed"] is False
    assert card["runtime_counts"]["ollama_llava_call_attempt"] is False
    assert card["retrieval_document"]["visual_guidance_only"] is True


def test_build_writes_summary_and_retrieval_docs(tmp_path: Path) -> None:
    mod = load_module()
    input_path = tmp_path / "gated.jsonl"
    output_dir = tmp_path / "out"
    docs = [
        {
            "document_id": "doc::p001",
            "page_id": "t_p_120_1176_p000001",
            "visual_route": "image_visual",
            "visual_subtype": "confirmed_diagram_dominant",
            "summary": "parts_diagram_or_illustrated_parts_list",
            "figure_refs": ["figure 2 sheet 1"],
            "part_numbers": ["120-41824-003"],
            "callouts": ["1", "210"],
        },
        {
            "document_id": "doc::p002",
            "page_id": "t_p_120_1176_p000002",
            "visual_route": "image_visual",
            "visual_subtype": "confirmed_diagram_dominant",
            "summary": "Technical drawing of a chair with armrests.",
            "figure_refs": ["figure 3"],
            "part_numbers": [],
            "callouts": ["Arrow pointing left"],
        },
    ]
    input_path.write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")

    args = mod.parse_args([
        "--gated-visual-documents-jsonl", str(input_path),
        "--output-dir", str(output_dir),
        "--min-summary-count", "2",
    ])

    summary = mod.build(args)

    assert summary["quality_status"] == "PASS"
    assert summary["confirmed_image_summary_count"] == 2
    assert summary["retrieval_document_count"] == 2
    assert summary["answer_permission_count"] == 0
    assert (output_dir / "trace_net_confirmed_image_page_summary_v1.jsonl").exists()
    assert (output_dir / "trace_net_confirmed_image_page_summary_v1_retrieval_documents.jsonl").exists()
