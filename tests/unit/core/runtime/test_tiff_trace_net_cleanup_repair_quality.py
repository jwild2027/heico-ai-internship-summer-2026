from __future__ import annotations

from pathlib import Path

from tiff.trace_net_cleanup_repair import (
    TraceNetCleanupRepairOptions,
    TraceNetCleanupRepairPaths,
    build_trace_net_cleanup_repair_quality,
    run_trace_net_cleanup_repairs,
    write_jsonl,
)


def test_cleanup_repair_quality_gate(tmp_path: Path) -> None:
    visual_dir = tmp_path / "visual_text"
    trace_dir = tmp_path / "trace_net"
    output_dir = trace_dir / "cleanup_repair"
    write_jsonl(
        visual_dir / "visual_text_extraction_clean.jsonl",
        [
            {
                "page_id": "p001",
                "status": "ok",
                "prompt_version": "visual_text_v2_2",
                "visual_text_markdown_clean": "# Page visual text\n\n## Page type\nunknown\n\n## Labels/callouts/part numbers\nbullet list of exact visible labels, callouts, item numbers, part numbers, quantities, references. If none visible, say so.",
                "visual_text_cleanup_scores": {"trust_tier": "D", "prompt_template_leakage_risk": True},
            }
        ],
    )
    write_jsonl(trace_dir / "trace_net_repair_plan.jsonl", [{"page_id": "p001", "primary_repair_route": "prompt_cleanup_repair_route"}])
    paths = TraceNetCleanupRepairPaths(visual_text_dir=visual_dir, trace_net_dir=trace_dir, output_dir=output_dir)
    run_trace_net_cleanup_repairs(paths, TraceNetCleanupRepairOptions(apply=True, backup=False))

    report = build_trace_net_cleanup_repair_quality(
        paths,
        min_input_records=1,
        min_repaired_records=1,
        max_remaining_prompt_template_leakage_records=0,
        require_applied=True,
    )

    assert report["status"] == "OK"
    assert report["summary"]["repaired_records"] == 1
    assert report["summary"]["applied_to_clean_records"] is True
