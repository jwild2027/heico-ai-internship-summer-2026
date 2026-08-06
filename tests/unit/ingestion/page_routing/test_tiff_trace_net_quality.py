from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net import TraceNetOptions, TraceNetPaths, build_and_write_trace_net_plan, build_trace_net_quality


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_trace_net_quality_gate_ok(tmp_path: Path) -> None:
    paths = TraceNetPaths(
        export_dir=tmp_path / "export",
        trait_dir=tmp_path / "traits",
        visual_text_dir=tmp_path / "visual",
        output_dir=tmp_path / "trace_net",
    )
    _write_json(
        paths.page_index_path,
        {
            "p1": {"page_id": "p1", "role": "table"},
            "p2": {"page_id": "p2", "role": "figure"},
        },
    )
    _write_jsonl(
        paths.clean_records_path,
        [
            {"page_id": "p1", "status": "ok", "prompt_version": "visual_text_v2_2", "scores": {"trust_tier": "C"}},
            {"page_id": "p2", "status": "ok", "prompt_version": "visual_text_v2_2", "scores": {"trust_tier": "B", "has_figure_description": True}},
        ],
    )
    build_and_write_trace_net_plan(paths, TraceNetOptions(expected_pages=2))

    quality = build_trace_net_quality(paths, min_records=2, expected_pages=2)

    assert quality["status"] == "OK"
    assert quality["summary"]["trace_net_records"] == 2
    assert quality["summary"]["trace_net_route_counts"]["table_grid"] == 1


def test_trace_net_quality_gate_fails_missing_artifacts(tmp_path: Path) -> None:
    paths = TraceNetPaths(output_dir=tmp_path / "trace_net")

    quality = build_trace_net_quality(paths, min_records=1)

    assert quality["status"] == "FAIL"
    failed = [check for check in quality["checks"] if check["status"] == "FAIL"]
    assert failed
