from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path("scripts/build/visual/build_trace_net_confirmed_image_llava_observations_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("llava_observations", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llava_observations"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_choose_cards_skips_existing_success(tmp_path: Path) -> None:
    mod = load_module()
    out = tmp_path / "obs.jsonl"
    out.write_text(json.dumps({
        "page_id": "t_p_120_1176_p000001",
        "llava_status": "ollama_llava_observation_created",
    }) + "\n", encoding="utf-8")

    cards = [
        {"page_id": "t_p_120_1176_p000001"},
        {"page_id": "t_p_120_1176_p000002"},
    ]

    selected = mod.choose_cards(cards, page_ids=[], limit=0, overwrite=False, output_jsonl=out)
    assert [c["page_id"] for c in selected] == ["t_p_120_1176_p000002"]


def test_convert_png_passes_through(tmp_path: Path) -> None:
    mod = load_module()
    img = tmp_path / "t_p_120_1176_p000001.png"
    img.write_bytes(b"not-real-png-but-path-test")

    out, note = mod.convert_image_for_ollama(img, converted_dir=tmp_path / "converted")

    assert out == img
    assert note == "source_image_passed_through"


def test_dry_run_record_is_safe_and_image_ready(tmp_path: Path) -> None:
    mod = load_module()
    img_root = tmp_path / "images"
    img_root.mkdir()
    img = img_root / "t_p_120_1176_p000001.png"
    img.write_bytes(b"fake")

    card = {
        "page_id": "t_p_120_1176_p000001",
        "document_id": "card-1",
        "visual_page_summary": {
            "visual_page_type": "technical_diagram_or_figure",
            "figure_refs_clean": ["figure 1"],
            "part_numbers": ["120-41824-003"],
        },
    }

    rec = mod.build_record(
        card,
        image_roots=[img_root],
        output_dir=tmp_path / "out",
        ollama_base_url="http://127.0.0.1:11434",
        llava_model="llava:13b",
        timeout_seconds=1.0,
        dry_run=True,
    )

    assert rec["llava_status"] == "dry_run_image_ready"
    assert rec["runtime_counts"]["ollama_llava_call_attempt"] is False
    assert rec["safety_contract"]["answer_permission"] is False
    assert rec["safety_contract"]["final_answer_allowed"] is False
