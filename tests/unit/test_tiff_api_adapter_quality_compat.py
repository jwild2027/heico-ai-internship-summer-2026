import json
from pathlib import Path

from tiff.api_adapter_quality import build_api_adapter_quality_report


def test_api_adapter_quality_accepts_current_readiness_shapes(tmp_path: Path) -> None:
    api = {
        "status": "OK",
        "backend_quality": "ok",
        "graph_nodes": 10,
        "page_contexts": 5,
        "source_links": 5,
        "part_probe": {"status": "ok", "pages": 3},
        "page_probe": {"status": "ok", "source": True, "context": True},
        "vector_trace_probe": {"status": "OK"},
    }
    storage = {
        "status": "OK",
        "mode": "local_artifacts",
        "organization_summary_present": True,
        "quality_status": "ok",
        "part_probe": {"found": True, "pages": 3},
        "page_probe": {"found": True, "source": True},
    }
    api_path = tmp_path / "api.json"
    storage_path = tmp_path / "storage.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")
    storage_path.write_text(json.dumps(storage), encoding="utf-8")

    report = build_api_adapter_quality_report(api_path, storage_path)
    assert report.status == "OK"
    assert report.summary["api_part_probe_ok"] is True
    assert report.summary["api_page_probe_source"] is True
    assert report.summary["storage_adapter_page_probe_source"] is True
