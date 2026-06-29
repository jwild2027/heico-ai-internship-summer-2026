import json
from pathlib import Path

from tiff.trace_net_four_route_storage_gate_v1 import build_four_route_storage_gate


def _source_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "final_validated_operational_route": "table",
                "final_do_not_embed": False,
                "qdrant_embedding_allowed": True,
                "opensearch_index_allowed": True,
                "retry_validation_decision": "already_validated",
            },
            {
                "page_id": "p2",
                "page_number": 2,
                "final_validated_operational_route": "plain_text",
                "final_do_not_embed": False,
                "qdrant_embedding_allowed": True,
                "opensearch_index_allowed": False,
                "retry_validation_decision": "retry_validated_primary_or_candidate_route",
            },
            {
                "page_id": "p3",
                "page_number": 3,
                "final_validated_operational_route": "blank",
                "final_do_not_embed": True,
                "qdrant_embedding_allowed": False,
                "opensearch_index_allowed": False,
                "retry_validation_decision": "already_validated",
            },
            {
                "page_id": "p4",
                "page_number": 4,
                "source_operational_route": "plain_text",
                "final_validated_operational_route": None,
                "final_do_not_embed": True,
                "retry_validation_decision": "validator_gated_unresolved_after_retry",
            },
        ],
    }


def test_build_four_route_storage_gate_writes_expected_outputs(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_source_payload()), encoding="utf-8")

    payload = build_four_route_storage_gate(
        route_unresolved_retry_probe_path=source,
        output_dir=tmp_path / "out",
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["storage_gate_record_count"] == 4
    assert summary["postgres_graph_record_count"] == 4
    assert summary["qdrant_embedding_allowed_count"] == 2
    assert summary["opensearch_index_allowed_count"] == 1
    assert summary["final_do_not_embed_count"] == 2
    assert summary["validator_gated_count"] == 1
    assert Path(summary["qdrant_candidates_jsonl_path"]).exists()
    assert Path(summary["opensearch_candidates_jsonl_path"]).exists()
    assert Path(summary["blocked_records_csv_path"]).exists()


def test_blank_never_enters_qdrant_or_opensearch(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"quality_status": "PASS", "records": [_source_payload()["records"][2]]}), encoding="utf-8")
    payload = build_four_route_storage_gate(
        route_unresolved_retry_probe_path=source,
        output_dir=tmp_path / "out",
    )
    record = payload["records"][0]
    assert record["final_validated_operational_route"] == "blank"
    assert record["postgres_graph_record"] is True
    assert record["qdrant_embedding_allowed"] is False
    assert record["opensearch_index_allowed"] is False
    assert record["final_do_not_embed"] is True


def test_unresolved_record_is_graph_only_blocked(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"quality_status": "PASS", "records": [_source_payload()["records"][3]]}), encoding="utf-8")
    payload = build_four_route_storage_gate(
        route_unresolved_retry_probe_path=source,
        output_dir=tmp_path / "out",
    )
    record = payload["records"][0]
    assert record["storage_decision"] == "graph_only_validator_gated"
    assert record["validator_gated"] is True
    assert record["qdrant_embedding_allowed"] is False
    assert record["opensearch_index_allowed"] is False
