from __future__ import annotations

import json
import zipfile
from argparse import Namespace
from pathlib import Path

from scripts import trace_net_tiff_to_answer_server_demo_v1 as demo


def test_find_record_exact_page_id():
    payload = {"records": [{"page_id": "t_p_x_p000001", "route": "table"}]}
    assert demo.find_record(payload, "t_p_x_p000001")["route"] == "table"


def test_find_record_page_number_fallback():
    payload = {"records": [{"page_number": 343, "value": "ok"}]}
    assert demo.find_record(payload, "t_p_120_1176_p000343")["value"] == "ok"


def test_score_member_prefers_exact_source_member():
    score, reason = demo.score_member("manual/page_0343.tif", ["manual/page_0343.tif"], demo.DEFAULT_PAGE_ID)
    assert score == 1000
    assert reason == "exact_source_member"


def test_extract_raw_tiff_from_zip(tmp_path: Path):
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manual/page_0343.tif", b"II*\x00fake")
    path, info = demo.extract_raw_tiff(archive_path, "manual/page_0343.tif", tmp_path / "out")
    assert path and path.exists()
    assert info["available"] is True
    assert info["byte_count"] == len(b"II*\x00fake")


def test_collect_citations_deduplicates():
    payload = {"items": [
        {"page_id": "p1", "page_number": 1},
        {"page_id": "p1", "page_number": 1},
        {"page_id": "p2", "page_number": 2},
    ]}
    rows = demo.collect_citations(payload)
    assert [row["page_id"] for row in rows] == ["p1", "p2"]


def test_graph_svg_escapes_untrusted_labels():
    svg = demo.make_graph_svg("<script>", "120-1-001", "120-2-001", [{"page_id": "<bad>"}])
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&lt;bad&gt;" in svg


def test_render_html_has_all_12_stages(tmp_path: Path):
    stages = [demo.Stage(i, name, "PASS", "summary") for i, name in enumerate(demo.STAGE_NAMES, 1)]
    result = demo.DemoResult(
        status=demo.STATUS,
        quality_status="PASS",
        page_id=demo.DEFAULT_PAGE_ID,
        question=demo.DEFAULT_QUESTION,
        answer="Answer\nEvidence\nLimits",
        stages=stages,
        artifacts={},
        output_dir=str(tmp_path),
        report_path=str(tmp_path / "report.html"),
        manifest_path=str(tmp_path / "report.json"),
        raw_preview_path=None,
        graph_path=str(tmp_path / "graph.svg"),
        live_endpoint_called=True,
        model_call_count=1,
        citations=[{"page_id": "p1"}],
        warnings=[],
        failures=[],
        safety={"read_only": True},
    )
    value = demo.render_html(result, None, demo.make_graph_svg(result.page_id, None, None, []), {})
    assert value.count('class="stage ') == 12
    assert "Raw TIFF → Validated Answer" in value
    assert "Answer\nEvidence\nLimits" in value


def test_source_contains_no_database_mutation_commands():
    source = Path(demo.__file__).read_text(encoding="utf-8").lower()
    # Tokens are declared as a safety lint vocabulary, so inspect executable call sites only.
    forbidden_calls = ("psql", "docker exec", "requests.put", "requests.delete", "method=\"put\"", "method=\"delete\"")
    assert not any(token in source for token in forbidden_calls)


def test_default_parser_is_read_only():
    args = demo.build_parser().parse_args([])
    assert args.live_ocr is True
    assert args.check_qdrant is True
    assert args.require_raw_tiff is False
    assert args.require_one_model_call is False
    assert args.min_citations == 0
    assert args.strict is False
