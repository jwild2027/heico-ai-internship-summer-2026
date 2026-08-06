import json
from pathlib import Path

from tiff.trace_net_route_unresolved_retry_probe_v1 import build_route_unresolved_retry_probe


def _source_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "source_operational_route": "table",
                "validated_operational_route": "table",
                "validation_decision": "validated_primary_route",
                "validation_status": "PASS",
                "final_do_not_embed": False,
                "qdrant_embedding_allowed": True,
                "opensearch_index_allowed": True,
                "ocr_word_count": 200,
                "part_number_count": 12,
                "ocr_sample_text": "120-12345-001 ASSY NUMBER CH-SEC-UN-FIG ITEM",
            },
            {
                "page_id": "p2",
                "page_number": 2,
                "source_operational_route": "table",
                "validation_decision": "validator_gated_unresolved",
                "validation_status": "VALIDATOR_GATED_UNRESOLVED",
                "final_do_not_embed": True,
                "route_subtype": "detailed_parts_list",
                "ocr_word_count": 240,
                "part_number_count": 8,
                "ocr_sample_text": "120-29067-035 120-29068-059 ASSY NUMBER CH-SEC-UN-FIG ITEM NOMENCLATURE",
            },
            {
                "page_id": "p3",
                "page_number": 3,
                "source_operational_route": "plain_text",
                "validation_decision": "validator_gated_unresolved",
                "validation_status": "VALIDATOR_GATED_UNRESOLVED",
                "final_do_not_embed": True,
                "route_subtype": "normal_text",
                "ocr_word_count": 120,
                "part_number_count": 0,
                "ocr_sample_text": "General description and operation. The seat consists of a structure and cushion.",
            },
            {
                "page_id": "p4",
                "page_number": 4,
                "source_operational_route": "blank",
                "validation_decision": "validator_gated_unresolved",
                "validation_status": "VALIDATOR_GATED_UNRESOLVED",
                "final_do_not_embed": True,
                "route_subtype": "blank_candidate",
                "ocr_word_count": 0,
                "part_number_count": 0,
                "ocr_sample_text": "",
            },
            {
                "page_id": "p5",
                "page_number": 5,
                "source_operational_route": "image",
                "validation_decision": "validator_gated_unresolved",
                "validation_status": "VALIDATOR_GATED_UNRESOLVED",
                "final_do_not_embed": True,
                "route_subtype": "image_visual_diagram",
                "ocr_word_count": 55,
                "part_number_count": 0,
                "ocr_sample_text": "Figure view seat belt backrest ashtray callout labels",
            },
            {
                "page_id": "p6",
                "page_number": 6,
                "source_operational_route": "plain_text",
                "validation_decision": "validator_gated_unresolved",
                "validation_status": "VALIDATOR_GATED_UNRESOLVED",
                "final_do_not_embed": True,
                "route_subtype": "review_required",
                "ocr_word_count": 5,
                "part_number_count": 0,
                "ocr_sample_text": "noise ? ?",
            },
        ],
    }


def test_build_retries_unresolved_and_preserves_validated(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_source_payload()), encoding="utf-8")

    payload = build_route_unresolved_retry_probe(
        route_validator_runner_path=source,
        output_dir=tmp_path / "out",
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["retry_probe_record_count"] == 6
    assert summary["retry_attempted_count"] == 5
    assert summary["retry_validated_count"] == 4
    assert summary["remaining_validator_gated_unresolved_count"] == 1
    assert summary["final_validated_route_count"] == 5
    assert summary["human_review_required_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0

    by_page = {r["page_id"]: r for r in payload["records"]}
    assert by_page["p1"]["retry_status"] == "not_needed_already_validated"
    assert by_page["p2"]["final_validated_operational_route"] == "table"
    assert by_page["p3"]["final_validated_operational_route"] == "plain_text"
    assert by_page["p4"]["final_validated_operational_route"] == "blank"
    assert by_page["p4"]["final_do_not_embed"] is True
    assert by_page["p5"]["final_validated_operational_route"] == "image"
    assert by_page["p6"]["final_validated_operational_route"] is None


def test_writes_expected_decision_files(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_source_payload()), encoding="utf-8")
    out = tmp_path / "out"

    build_route_unresolved_retry_probe(route_validator_runner_path=source, output_dir=out, quality=True)

    assert (out / "trace_net_route_unresolved_retry_probe_v1.json").exists()
    assert (out / "trace_net_route_unresolved_retry_probe_v1_records.csv").exists()
    assert (out / "trace_net_route_unresolved_retry_probe_v1_validated_records.csv").exists()
    assert (out / "trace_net_route_unresolved_retry_probe_v1_unresolved_records.csv").exists()
