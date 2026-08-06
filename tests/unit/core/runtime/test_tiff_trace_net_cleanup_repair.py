from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_cleanup_repair import (
    TraceNetCleanupRepairOptions,
    TraceNetCleanupRepairPaths,
    read_jsonl,
    repair_cleanup_record,
    run_trace_net_cleanup_repairs,
    write_jsonl,
)


def _record(page_id: str, markdown: str, tier: str = "D") -> dict:
    return {
        "page_id": page_id,
        "status": "ok",
        "prompt_version": "visual_text_v2_2",
        "visual_text_markdown_clean": markdown,
        "visual_text_cleanup_scores": {
            "trust_tier": tier,
            "prompt_template_leakage_risk": tier == "D",
            "section_bleed_risk": tier == "D",
            "usable_for_rag": tier in {"A", "B"},
            "requires_human_review": tier in {"C", "D"},
        },
    }


def test_repair_record_removes_prompt_template_and_splits_section_bleed() -> None:
    markdown = """# Page visual text

## Page type
parts_list

## Transcribed visible text
- 120-12345-001 Visual summary: This page lists visible part numbers. Labels/callouts/part numbers: bullet list of exact visible labels, callouts, item numbers, part numbers, quantities, references. If none visible, say so.

## Visual summary
No summary.

## Labels/callouts/part numbers
bullet list of exact visible labels, callouts, item numbers, part numbers, quantities, references. If none visible, say so.
"""
    repaired = repair_cleanup_record(_record("p001", markdown))
    text = repaired["visual_text_markdown_clean"].lower()
    cleanup = repaired["visual_text_cleanup_scores"]

    assert "bullet list of exact visible" not in text
    assert "if none visible" not in text
    assert "## visual summary" in text
    assert cleanup["prompt_template_leakage_risk"] is False
    assert cleanup["section_bleed_risk"] is False
    assert cleanup["trust_tier"] in {"A", "B", "C"}


def test_run_cleanup_repairs_selects_only_planned_route(tmp_path: Path) -> None:
    visual_dir = tmp_path / "visual_text"
    trace_dir = tmp_path / "trace_net"
    output_dir = trace_dir / "cleanup_repair"
    write_jsonl(
        visual_dir / "visual_text_extraction_clean.jsonl",
        [
            _record("p001", "# Page visual text\n\n## Page type\nunknown\n\n## Labels/callouts/part numbers\nbullet list of exact visible labels. If none visible, say so."),
            _record("p002", "# Page visual text\n\n## Page type\nunknown\n\n## Visual summary\nClean enough.", tier="B"),
        ],
    )
    write_jsonl(
        trace_dir / "trace_net_repair_plan.jsonl",
        [
            {"page_id": "p001", "primary_repair_route": "prompt_cleanup_repair_route", "primary_repair_action": "rerun_cleanup_salvage"},
            {"page_id": "p002", "primary_repair_route": "rag_include_route", "primary_repair_action": "no_repair_needed"},
        ],
    )
    paths = TraceNetCleanupRepairPaths(visual_text_dir=visual_dir, trace_net_dir=trace_dir, output_dir=output_dir)
    result = run_trace_net_cleanup_repairs(paths, TraceNetCleanupRepairOptions(apply=False))

    summary = result["summary"]
    assert summary["records"] == 2
    assert summary["selected_records"] == 1
    assert summary["repaired_records"] == 1
    assert output_dir.joinpath("trace_net_cleanup_repaired_records.jsonl").exists()
    records = read_jsonl(output_dir / "trace_net_cleanup_repaired_records.jsonl")
    assert records[0]["trace_net_cleanup_repair"]["applied"] is True
    assert "trace_net_cleanup_repair" not in records[1]


def test_apply_rewrites_clean_records_with_backup(tmp_path: Path) -> None:
    visual_dir = tmp_path / "visual_text"
    trace_dir = tmp_path / "trace_net"
    output_dir = trace_dir / "cleanup_repair"
    clean_path = visual_dir / "visual_text_extraction_clean.jsonl"
    write_jsonl(clean_path, [_record("p001", "# Page visual text\n\n## Page type\nunknown\n\n## Labels/callouts/part numbers\nbullet list of exact visible labels. If none visible, say so.")])
    write_jsonl(trace_dir / "trace_net_repair_plan.jsonl", [{"page_id": "p001", "primary_repair_route": "prompt_cleanup_repair_route"}])
    paths = TraceNetCleanupRepairPaths(visual_text_dir=visual_dir, trace_net_dir=trace_dir, output_dir=output_dir)
    result = run_trace_net_cleanup_repairs(paths, TraceNetCleanupRepairOptions(apply=True, backup=True))

    assert result["summary"]["applied_to_clean_records"] is True
    assert result["summary"]["backups"]
    applied = read_jsonl(clean_path)
    assert applied[0]["cleanup_version"] == "trace_net_cleanup_repair_v1"
