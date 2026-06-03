from __future__ import annotations

from pathlib import Path

from tiff.trace_net_repair import (
    TraceNetRepairOptions,
    TraceNetRepairPaths,
    build_and_write_trace_net_repair_plan,
    build_trace_net_repair_quality,
    write_jsonl,
)


def _record(page_id: str, tier: str, page_role: str | None = None, image_class: str | None = None, **flags: bool) -> dict:
    rec = {
        "page_id": page_id,
        "status": "ok",
        "prompt_version": "visual_text_v2_2",
        "visual_text_cleanup_scores": {
            "trust_tier": tier,
            "usable_for_rag": tier in {"A", "B"},
            "requires_human_review": tier in {"C", "D"} or any(flags.values()),
            **flags,
        },
        "visual_text_scores_clean": dict(flags),
    }
    if page_role or image_class:
        rec["source"] = {"page_role": page_role, "image_class": image_class}
    return rec


def test_repair_quality_gate(tmp_path: Path) -> None:
    visual_dir = tmp_path / "visual_text"
    trust_dir = tmp_path / "trust_traits"
    output_dir = tmp_path / "trace_net"
    records = [
        _record("p001", "D", prompt_template_leakage_risk=True),
        _record("p002", "D", page_role="table", image_class="likely_table_or_grid", table_expected_but_not_extracted=True),
    ]
    write_jsonl(visual_dir / "visual_text_extraction_clean.jsonl", records)
    write_jsonl(
        trust_dir / "trust_trait_assertions.jsonl",
        [
            {"page_id": "p001", "trait_type": "trust", "trait_key": "visual_text", "trait_value": "D"},
            {"page_id": "p001", "trait_type": "review", "trait_key": "visual_text", "trait_value": "prompt_template_leakage"},
            {"page_id": "p002", "trait_type": "trust", "trait_key": "visual_text", "trait_value": "D"},
            {"page_id": "p002", "trait_type": "review", "trait_key": "visual_text", "trait_value": "table_expected_but_not_extracted"},
        ],
    )
    paths = TraceNetRepairPaths(visual_text_dir=visual_dir, trust_trait_dir=trust_dir, output_dir=output_dir)
    build_and_write_trace_net_repair_plan(paths, TraceNetRepairOptions(expected_pages=2))

    quality = build_trace_net_repair_quality(
        paths,
        min_records=2,
        expected_pages=2,
        min_auto_repair_candidates=2,
        max_unplanned_problem_records=0,
    )

    assert quality["status"] == "OK"
    assert quality["summary"]["trace_net_repair_records"] == 2
    assert quality["summary"]["trace_net_repair_auto_repair_candidate_records"] == 2
    assert quality["summary"]["trace_net_repair_table_repair_records"] == 1
    assert quality["summary"]["trace_net_repair_table_repair_high_records"] == 1
