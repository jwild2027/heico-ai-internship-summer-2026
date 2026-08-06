from __future__ import annotations

import json
from pathlib import Path

from tiff.api_adapter_quality import build_api_adapter_quality_report, write_api_adapter_quality_report


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_api_adapter_quality_accepts_machine_readable_probe_dicts(tmp_path: Path) -> None:
    api = tmp_path / "api.json"
    storage = tmp_path / "storage.json"
    _write(api, {
        "status": "OK",
        "backend_quality": "ok",
        "graph_nodes": 3788,
        "page_contexts": 509,
        "source_links": 509,
        "part_probe": {"ok": True, "pages": 28},
        "page_probe": {"ok": True, "source": True, "context": True},
        "vector_trace_probe": {"status": "OK"},
    })
    _write(storage, {
        "status": "OK",
        "mode": "local_artifacts",
        "organization_summary_present": True,
        "quality_status": "ok",
        "part_probe": {"found": True, "pages": 28},
        "page_probe": {"found": True, "source": True},
    })
    report = build_api_adapter_quality_report(api, storage)
    assert report.status == "OK"
    assert report.summary["api_part_probe_ok"] is True
    assert report.summary["api_part_probe_pages"] == 28
    assert report.summary["storage_adapter_page_probe_source"] is True


def test_api_adapter_quality_accepts_current_human_readable_probe_strings(tmp_path: Path) -> None:
    api = tmp_path / "api.json"
    storage = tmp_path / "storage.json"
    _write(api, {
        "status": "OK",
        "backend_quality": "ok",
        "graph_nodes": 3788,
        "page_contexts": 509,
        "source_links": 509,
        "part_probe": "120-37313-001 | ok | pages=28 | name=HOLDER, MAGAZINE",
        "page_probe": "t_p_120_1176_p000083 | ok | source=True | context=True",
        "vector_trace_probe": "t_p_120_1176_p000495 | OK",
    })
    _write(storage, {
        "status": "OK",
        "mode": "local_artifacts",
        "organization_summary_present": True,
        "quality_status": "ok",
        "part_probe": "120-37313-001 | found=True | name=HOLDER, MAGAZINE | pages=28",
        "page_probe": "t_p_120_1176_p000083 | found=True | source=True",
    })
    report = build_api_adapter_quality_report(api, storage)
    assert report.status == "OK"
    assert report.summary["api_part_probe_ok"] is True
    assert report.summary["api_page_probe_ok"] is True
    assert report.summary["api_vector_trace_probe_ok"] is True
    assert report.summary["storage_adapter_part_probe_found"] is True
    assert report.summary["storage_adapter_page_probe_source"] is True


def test_api_adapter_quality_missing_reports_fail(tmp_path: Path) -> None:
    report = build_api_adapter_quality_report(tmp_path / "missing_api.json", tmp_path / "missing_storage.json")
    assert report.status == "FAIL"
    assert any(check.name == "api_ready_report_present" and check.status == "FAIL" for check in report.checks)
    assert any(check.name == "storage_adapter_ready_report_present" and check.status == "FAIL" for check in report.checks)


def test_write_api_adapter_quality_report(tmp_path: Path) -> None:
    api = tmp_path / "api.json"
    storage = tmp_path / "storage.json"
    _write(api, {"status": "OK", "graph_nodes": 1, "page_contexts": 1, "source_links": 1, "part_probe": "ok pages=1", "page_probe": "ok source=True", "vector_trace_probe": "OK"})
    _write(storage, {"status": "OK", "organization_summary_present": True, "part_probe": "found=True pages=1", "page_probe": "found=True source=True", "quality_status": "ok"})
    report = build_api_adapter_quality_report(api, storage)
    out = write_api_adapter_quality_report(report, tmp_path / "quality.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "OK"
    assert data["summary"]["storage_adapter_ready_present"] is True
