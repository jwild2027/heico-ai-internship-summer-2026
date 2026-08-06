import json
from pathlib import Path

from tiff.trace_net_route_validator_runner_v1 import build_route_validator_runner


def _source_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_number": 1,
                "page_id": "p1",
                "operational_route": "blank",
                "route_subtype": "blank_candidate",
                "route_confidence_band": "high",
                "route_confidence_score": 98,
                "ocr_text_word_count": 0,
                "part_number_count": 0,
                "auto_resolved": True,
            },
            {
                "page_number": 2,
                "page_id": "p2",
                "operational_route": "plain_text",
                "route_subtype": "procedure_or_description",
                "route_confidence_band": "medium",
                "route_confidence_score": 82,
                "ocr_text_word_count": 140,
                "part_number_count": 0,
                "validator_required": True,
                "signal_counts": {"procedure_term_count": 2, "has_row_structure": False},
            },
            {
                "page_number": 3,
                "page_id": "p3",
                "operational_route": "table",
                "route_subtype": "detailed_parts_list",
                "route_confidence_band": "medium",
                "route_confidence_score": 82,
                "ocr_text_word_count": 200,
                "part_number_count": 20,
                "validator_required": True,
                "signal_counts": {"has_row_structure": True, "detailed_parts_term_count": 2},
            },
            {
                "page_number": 4,
                "page_id": "p4",
                "operational_route": "image",
                "route_subtype": "image_visual_diagram",
                "legacy_route": "image_visual",
                "route_confidence_band": "high",
                "route_confidence_score": 90,
                "ocr_text_word_count": 45,
                "part_number_count": 0,
                "signal_counts": {"has_figure_caption": True, "concrete_visual_term_count": 2, "has_row_structure": False},
            },
            {
                "page_number": 5,
                "page_id": "p5",
                "operational_route": "plain_text",
                "route_subtype": "review_required",
                "secondary_operational_routes": ["table"],
                "route_confidence_band": "low",
                "route_confidence_score": 0,
                "ocr_text_word_count": 220,
                "part_number_count": 15,
                "validator_required": True,
                "multi_route_required": True,
                "signal_counts": {"has_row_structure": True, "table_index_term_count": 1},
            },
        ],
    }


def test_validates_four_routes_and_secondary_route(tmp_path):
    source = tmp_path / "four_route.json"
    source.write_text(json.dumps(_source_payload()), encoding="utf-8")

    payload = build_route_validator_runner(
        four_route_resolver=source,
        output_dir=tmp_path / "out",
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["validator_record_count"] == 5
    assert summary["validated_route_count"] == 5
    assert summary["validated_secondary_route_count"] == 1
    assert summary["validated_operational_route_counts"]["blank"] == 1
    assert summary["validated_operational_route_counts"]["plain_text"] == 1
    assert summary["validated_operational_route_counts"]["table"] == 2
    assert summary["validated_operational_route_counts"]["image"] == 1

    p5 = [r for r in payload["records"] if r["page_id"] == "p5"][0]
    assert p5["validated_operational_route"] == "table"
    assert p5["validation_decision"] == "validated_secondary_route"
    assert p5["opensearch_index_allowed"] is True


def test_unresolved_stays_do_not_embed(tmp_path):
    source = tmp_path / "four_route.json"
    source.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {
                "page_number": 9,
                "page_id": "p9",
                "operational_route": "image",
                "route_subtype": "image_visual_diagram",
                "ocr_text_word_count": 300,
                "part_number_count": 25,
                "signal_counts": {"has_row_structure": True, "ipl_visual_blocker": True},
                "validator_required": True,
            }
        ],
    }), encoding="utf-8")

    payload = build_route_validator_runner(
        four_route_resolver=source,
        output_dir=tmp_path / "out",
        quality=True,
    )
    record = payload["records"][0]
    assert record["validated_operational_route"] is None
    assert record["final_do_not_embed"] is True
    assert record["qdrant_embedding_allowed"] is False
    assert payload["summary"]["validator_gated_unresolved_count"] == 1
