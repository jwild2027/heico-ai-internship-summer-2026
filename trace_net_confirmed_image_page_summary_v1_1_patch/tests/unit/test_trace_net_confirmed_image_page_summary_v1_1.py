from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path("scripts/build_trace_net_confirmed_image_page_summary_v1_1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("confirmed_image_summary_v1_1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["confirmed_image_summary_v1_1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_recursive_figure_ref_harvest_from_nested_search_text() -> None:
    mod = load_module()
    doc = {
        "page_id": "t_p_120_1176_p000172",
        "visual_route": "image_visual",
        "visual_subtype": "confirmed_diagram_dominant",
        "retrieval_payload": {
            "source": {
                "search_text": "Passenger seat diagram. See Figure 26 Sheet 1 and part 120-36833-517."
            }
        },
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

    assert "figure 26 sheet 1" in card["visual_page_summary"]["figure_refs_clean"]
    assert "120-36833-517" in card["visual_page_summary"]["part_numbers"]


def test_nested_figure_ref_keys_and_dict_metadata_are_cleaned() -> None:
    mod = load_module()
    doc = {
        "page_id": "t_p_120_1176_p000499",
        "visual_route": "image_visual",
        "visual_subtype": "confirmed_diagram_dominant",
        "identifiers": {
            "figure_references": [
                "{'type': 'diagram', 'description': 'A technical drawing or schematic.'}",
                "figure 609",
            ],
            "part_numbers": [],
        },
        "summary": "The image contains technical drawings and assembly diagram signals.",
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

    assert "figure 609" in card["visual_page_summary"]["figure_refs_clean"]
    assert card["visual_page_summary"]["structured_visual_metadata"]
    assert any("dict-like" in x for x in card["visual_page_summary"]["uncertainty"])


def test_build_writes_v1_1_outputs(tmp_path: Path) -> None:
    mod = load_module()
    input_path = tmp_path / "gated.jsonl"
    output_dir = tmp_path / "out"
    docs = [
        {
            "document_id": "doc::p001",
            "page_id": "t_p_120_1176_p000001",
            "visual_route": "image_visual",
            "visual_subtype": "confirmed_diagram_dominant",
            "summary": "parts_diagram_or_illustrated_parts_list with Figure 2 Sheet 1",
            "part_numbers": ["120-41824-003"],
            "callouts": ["1", "210"],
        }
    ]
    input_path.write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")

    args = mod.parse_args([
        "--gated-visual-documents-jsonl", str(input_path),
        "--output-dir", str(output_dir),
        "--min-summary-count", "1",
    ])

    summary = mod.build(args)

    assert summary["quality_status"] == "PASS"
    assert summary["confirmed_image_summary_count"] == 1
    assert summary["pages_with_clean_figure_refs"] == 1
    assert (output_dir / "trace_net_confirmed_image_page_summary_v1_1.jsonl").exists()
    assert (output_dir / "trace_net_confirmed_image_page_summary_v1_1_retrieval_documents.jsonl").exists()
