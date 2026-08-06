from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_dry_run_loader_planner_v1 import build_dry_run_loader_planner


def _sample_storage_gate(path: Path) -> Path:
    payload = {
        "quality_status": "PASS",
        "summary": {
            "postgres_graph_record_count": 4,
            "qdrant_embedding_allowed_count": 2,
            "opensearch_index_allowed_count": 1,
            "final_do_not_embed_count": 2,
        },
        "records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "final_validated_operational_route": "plain_text",
                "storage_decision": "validated_graph_and_semantic_index",
                "postgres_graph_record": True,
                "qdrant_embedding_allowed": True,
                "opensearch_index_allowed": False,
                "final_do_not_embed": False,
                "validator_gated": False,
            },
            {
                "page_id": "p2",
                "page_number": 2,
                "final_validated_operational_route": "table",
                "storage_decision": "validated_graph_semantic_and_exact_index",
                "postgres_graph_record": True,
                "qdrant_embedding_allowed": True,
                "opensearch_index_allowed": True,
                "final_do_not_embed": False,
                "validator_gated": False,
            },
            {
                "page_id": "p3",
                "page_number": 3,
                "final_validated_operational_route": "blank",
                "storage_decision": "graph_only_blank",
                "postgres_graph_record": True,
                "qdrant_embedding_allowed": False,
                "opensearch_index_allowed": False,
                "final_do_not_embed": True,
                "validator_gated": False,
            },
            {
                "page_id": "p4",
                "page_number": 4,
                "final_validated_operational_route": "plain_text",
                "storage_decision": "graph_only_validator_gated",
                "postgres_graph_record": True,
                "qdrant_embedding_allowed": False,
                "opensearch_index_allowed": False,
                "final_do_not_embed": True,
                "validator_gated": True,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_dry_run_loader_planner_counts(tmp_path: Path) -> None:
    source = _sample_storage_gate(tmp_path / "storage.json")
    payload = build_dry_run_loader_planner(
        four_route_storage_gate=source,
        output_dir=tmp_path / "out",
        quality=True,
    )
    summary = payload["summary"]
    assert payload["quality_status"] == "PASS"
    assert summary["loader_plan_record_count"] == 4
    assert summary["postgres_dry_run_plan_count"] == 4
    assert summary["qdrant_dry_run_plan_count"] == 2
    assert summary["opensearch_dry_run_plan_count"] == 1
    assert summary["blocked_loader_record_count"] == 2
    assert summary["dry_run_only"] is True
    assert summary["live_write_enabled"] is False
    assert summary["write_attempt_count"] == 0


def test_dry_run_loader_planner_writes_decision_files(tmp_path: Path) -> None:
    source = _sample_storage_gate(tmp_path / "storage.json")
    out = tmp_path / "out"
    build_dry_run_loader_planner(four_route_storage_gate=source, output_dir=out)
    assert (out / "trace_net_dry_run_loader_planner_v1.json").exists()
    assert (out / "trace_net_dry_run_loader_planner_v1_postgres_dry_run_plan.jsonl").exists()
    assert (out / "trace_net_dry_run_loader_planner_v1_qdrant_dry_run_plan.jsonl").exists()
    assert (out / "trace_net_dry_run_loader_planner_v1_opensearch_dry_run_plan.jsonl").exists()
    assert (out / "trace_net_dry_run_loader_planner_v1_blocked_records.csv").exists()


def test_opensearch_requires_validated_table_route(tmp_path: Path) -> None:
    source = _sample_storage_gate(tmp_path / "storage.json")
    payload = build_dry_run_loader_planner(four_route_storage_gate=source, output_dir=tmp_path / "out")
    os_records = payload["opensearch_dry_run_plan_records"]
    assert len(os_records) == 1
    assert os_records[0]["route"] == "table"
