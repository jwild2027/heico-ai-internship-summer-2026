from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_query_api_v1 import (
    ApiQualityThresholds,
    check_graph_query_api_quality,
    make_api_report,
)


def _helper(path: Path, quality_status: str = "PASS") -> Path:
    payload = {
        "status": "GRAPH_QUERY_HELPER_BUILT",
        "quality_status": quality_status,
        "summary": {"graph_node_count": 1, "graph_edge_count": 1},
        "query_records": [
            {"query_type": "part_lookup", "input": {"part_number": "P1"}, "pages": [], "can_answer_directly": False, "can_prove_claims": False},
            {"query_type": "page_lookup", "input": {"page_id_or_label": "PAGE1"}, "pages": [], "can_answer_directly": False, "can_prove_claims": False},
            {"query_type": "ata_browse", "input": {"ata_code": "25-21-00"}, "pages": [], "can_answer_directly": False, "can_prove_claims": False},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_quality_passes_for_good_report(tmp_path: Path) -> None:
    report = make_api_report(_helper(tmp_path / "helper.json"))
    quality = check_graph_query_api_quality(
        report,
        thresholds=ApiQualityThresholds(
            min_route_records=5,
            min_query_records=3,
            require_helper_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert quality["quality_status"] == "PASS"


def test_quality_requires_helper_pass_when_enabled(tmp_path: Path) -> None:
    report = make_api_report(_helper(tmp_path / "helper.json", quality_status="FAIL"))
    quality = check_graph_query_api_quality(
        report,
        thresholds=ApiQualityThresholds(require_helper_quality_pass=True),
    )
    assert quality["quality_status"] == "FAIL"
    assert any("helper" in f for f in quality["failures"])


def test_quality_requires_minimum_route_count(tmp_path: Path) -> None:
    report = make_api_report(_helper(tmp_path / "helper.json"))
    quality = check_graph_query_api_quality(
        report,
        thresholds=ApiQualityThresholds(min_route_records=99),
    )
    assert quality["quality_status"] == "FAIL"
    assert any("route_record_count" in f for f in quality["failures"])
