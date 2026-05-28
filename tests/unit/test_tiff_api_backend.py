from __future__ import annotations

import json
from pathlib import Path

from tiff.api_backend import (
    check_api_ready,
    find_ata,
    find_page,
    find_part,
    get_organization_summary,
    get_status,
    load_api_data,
    make_paths,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _fixture(tmp_path: Path):
    export = tmp_path / "local_data" / "organization" / "export"
    _write_json(export / "manual_ata_tree.json", {"manuals": []})
    _write_json(
        export / "ata_tree.json",
        {
            "25-21-00": {
                "ata": "25-21-00",
                "manual": "T.P. 120/1176",
                "pages": [{"page_id": "p1", "page_label": "1056"}],
                "parts": 3,
            }
        },
    )
    _write_json(
        export / "part_tree.json",
        {
            "120-37313-001": {
                "part_number": "120-37313-001",
                "nomenclature": "HOLDER, MAGAZINE",
                "pages": [{"page_id": "p1", "source_url": "http://example/page"}],
                "mentions": 1,
            }
        },
    )
    _write_json(
        export / "page_index.json",
        {
            "p1": {
                "page_id": "p1",
                "ata": "25-21-00",
                "page_label": "1056",
                "source_url": "http://example/page",
                "tiff_path": "page.tif",
                "ocr_path": "page.txt",
            }
        },
    )
    _write_json(
        export / "organization_summary.json",
        {"counts": {"manuals": 1, "pages": 1, "ata_groups": 1, "parts": 1, "part_mentions": 1}},
    )
    _write_json(tmp_path / "local_data" / "pipeline_runs" / "latest_backend_pipeline.json", {"status": "ok", "run_id": "run1", "sqlite_counts": {"pages": 1}})
    _write_json(tmp_path / "local_data" / "pipeline_runs" / "latest_quality_gate.json", {"status": "ok", "summary": {"eval_failures": 0}, "checks": []})
    (tmp_path / "local_config.yaml").write_text("x: y\n", encoding="utf-8")
    return make_paths(repo_root=tmp_path)


def test_check_api_ready_ok(tmp_path: Path):
    paths = _fixture(tmp_path)
    result = check_api_ready(paths)
    assert result["status"] == "OK"
    assert result["quality_status"] == "ok"
    assert result["organization_summary"]["pages"] == 1


def test_load_and_query_api_data(tmp_path: Path):
    data = load_api_data(_fixture(tmp_path))
    assert get_status(data)["run_id"] == "run1"
    assert get_organization_summary(data)["parts"] == 1
    assert find_part(data, "120-37313-001")["nomenclature"] == "HOLDER, MAGAZINE"
    assert find_ata(data, "25-21-00")["manual"] == "T.P. 120/1176"
    assert find_page(data, "p1")["source_url"] == "http://example/page"


def test_check_api_ready_reports_missing_files(tmp_path: Path):
    paths = make_paths(repo_root=tmp_path)
    result = check_api_ready(paths)
    assert result["status"] == "NEEDS_ATTENTION"
    assert result["errors"]
