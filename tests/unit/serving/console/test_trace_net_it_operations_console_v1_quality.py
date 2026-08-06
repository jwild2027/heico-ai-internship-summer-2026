from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_it_operations_console_v1 import build_it_operations_console, check_it_operations_console_quality


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_quality_report_passes_clean_console(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(root / "stage" / "stage_quality.json", {"status": "PASS", "unsafe_record_count": 0})
    report = build_it_operations_console(root, tmp_path / "out")
    quality = check_it_operations_console_quality(Path(report["report_path"]), write_json_report=True)
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()


def test_quality_report_fails_when_stage_failed(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(root / "stage" / "stage_quality.json", {"status": "FAIL", "unsafe_record_count": 0})
    report = build_it_operations_console(root, tmp_path / "out")
    quality = check_it_operations_console_quality(Path(report["report_path"]))
    assert quality["status"] == "FAIL"
    assert quality["stage_fail_count"] == 1
