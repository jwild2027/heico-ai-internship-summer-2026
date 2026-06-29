import json
from pathlib import Path

from tiff.trace_net_four_route_operational_resolver_v1 import build_four_route_operational_resolver


def _write_source(path: Path, records):
    payload = {"quality_status": "PASS", "summary": {"resolver_record_count": len(records)}, "records": records}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_maps_detailed_subtypes_to_four_routes(tmp_path):
    source = tmp_path / "resolver.json"
    _write_source(source, [
        {"page_number": 1, "page_id": "p1", "primary_route": "blank_candidate", "route_confidence_band": "high", "route_confidence_score": 98, "auto_resolved": True},
        {"page_number": 2, "page_id": "p2", "primary_route": "procedure_or_description", "route_confidence_band": "high", "route_confidence_score": 90, "auto_resolved": True},
        {"page_number": 3, "page_id": "p3", "primary_route": "detailed_parts_list", "route_confidence_band": "high", "route_confidence_score": 94, "auto_resolved": True},
        {"page_number": 4, "page_id": "p4", "primary_route": "image_visual_diagram", "route_confidence_band": "high", "route_confidence_score": 90, "auto_resolved": True},
    ])
    payload = build_four_route_operational_resolver(route_confidence_resolver=source, output_dir=tmp_path / "out", quality=True)
    assert payload["quality_status"] == "PASS"
    routes = [r["operational_route"] for r in payload["records"]]
    assert routes == ["blank", "plain_text", "table", "image"]
    assert payload["summary"]["human_review_required_count"] == 0
    assert payload["summary"]["manual_review_required_count"] == 0


def test_mixed_text_and_figure_gets_secondary_plain_text(tmp_path):
    source = tmp_path / "resolver.json"
    _write_source(source, [
        {"page_number": 10, "page_id": "p10", "primary_route": "mixed_text_and_figure", "route_confidence_band": "medium", "route_confidence_score": 70, "auto_resolved": False, "validator_required": True},
    ])
    payload = build_four_route_operational_resolver(route_confidence_resolver=source, output_dir=tmp_path / "out")
    record = payload["records"][0]
    assert record["operational_route"] == "image"
    assert "plain_text" in record["secondary_operational_routes"]
    assert record["validator_required"] is True
    assert record["do_not_embed"] is True


def test_review_required_falls_back_to_candidate_route_without_human_review(tmp_path):
    source = tmp_path / "resolver.json"
    _write_source(source, [
        {"page_number": 20, "page_id": "p20", "primary_route": "review_required", "candidate_routes": ["table_or_index", "normal_text"], "route_confidence_band": "low", "route_confidence_score": 0, "validator_required": True},
    ])
    payload = build_four_route_operational_resolver(route_confidence_resolver=source, output_dir=tmp_path / "out")
    record = payload["records"][0]
    assert record["operational_route"] == "table"
    assert record["route_subtype"] == "review_required"
    assert record["human_review_required"] is False
    assert record["validator_required"] is True
    assert record["multi_route_required"] is True
