from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_extraction_quality import (
    VisualTextQualityPaths,
    build_visual_text_extraction_quality,
    write_visual_text_extraction_quality,
)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _make_quality_fixture(tmp_path: Path) -> VisualTextQualityPaths:
    paths = VisualTextQualityPaths(output_dir=tmp_path)
    summary = {
        "status": "OK",
        "provider": "mock",
        "model": "mock-vision-model",
        "total_page_cards": 2,
        "selected_pages": 1,
        "records": 1,
        "ok_records": 1,
        "planned_records": 0,
        "error_records": 0,
        "pages_with_visual_text": 1,
        "visual_text_char_total": 120,
        "visual_text_avg_chars": 120.0,
    }
    _write_json(paths.summary_path, summary)
    _write_jsonl(paths.records_path, [{"page_id": "p1", "status": "ok", "char_count": 120}])
    paths.corpus_md_path.write_text("# Page visual text\nhello", encoding="utf-8")
    _write_json(paths.graph_nodes_path, {"nodes": [{"id": "v1"}, {"id": "e1"}]})
    _write_json(paths.graph_edges_path, {"edges": [{"source": "p1", "target": "v1"}]})
    return paths


def test_visual_text_quality_ok_for_complete_overlay(tmp_path: Path) -> None:
    paths = _make_quality_fixture(tmp_path)

    report = build_visual_text_extraction_quality(paths)

    assert report["status"] == "OK"
    assert report["summary"]["visual_text_ok_records"] == 1


def test_visual_text_quality_fails_when_missing_artifacts(tmp_path: Path) -> None:
    report = build_visual_text_extraction_quality(VisualTextQualityPaths(output_dir=tmp_path))

    assert report["status"] == "FAIL"
    assert any(not check["ok"] for check in report["checks"])


def test_write_visual_text_quality_writes_json(tmp_path: Path) -> None:
    paths = _make_quality_fixture(tmp_path)

    report = write_visual_text_extraction_quality(paths)

    assert report["status"] == "OK"
    assert paths.quality_path.exists()
