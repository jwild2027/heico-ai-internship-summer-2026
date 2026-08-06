from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tiff.trace_net_e2e_query_input_v1 import (
    QUALITY_PASS,
    QueryBuildConfig,
    build_query_records,
    build_report,
    classify_query,
    read_queries_from_file,
)


def test_classifies_part_number_query() -> None:
    plan = classify_query("Find part number 120-36833-001")
    assert plan["query_intent"] == "covered_part_number"
    assert "table" in plan["requested_routes"]
    assert "table_exact_search" in plan["retrieval_channels"]
    assert {t["term_type"] for t in plan["query_terms"]} >= {"part_number"}


def test_classifies_manual_page_query() -> None:
    plan = classify_query("Where is manual reference 25-21-00 used?")
    assert plan["query_intent"] == "manual_page_reference"
    assert "table_hybrid_retrieval_bridge" in plan["retrieval_channels"]


def test_classifies_ipl_item_query() -> None:
    plan = classify_query("Find IPL item 130")
    assert plan["query_intent"] == "ipl_figure_item_or_quantity"
    assert "table" in plan["requested_routes"]


def test_build_records_are_retrieval_only() -> None:
    records = build_query_records([
        "Find part number 120-36833-001",
        "Where is manual reference 25-21-00 used?",
        "Find IPL item 130",
    ])
    assert len(records) == 3
    for record in records:
        assert record["safety_contract"]["answer_permission"] is False
        assert record["safety_contract"]["can_answer_directly"] is False
        assert record["safety_contract"]["can_prove_claims"] is False
        assert record["safety_contract"]["source_truth_mutation_allowed"] is False


def test_build_report_quality_passes() -> None:
    report = build_report(
        [
            "Find part number 120-36833-001",
            "Where is manual reference 25-21-00 used?",
            "Find IPL item 130",
            "Search table text MAINTENANCE MANUAL WITH",
            "What maintenance manual pages mention covered part numbers?",
        ],
        QueryBuildConfig(
            min_query_records=5,
            min_routeable_queries=5,
            min_unique_intents=4,
            min_planned_retrieval_queries=5,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == QUALITY_PASS
    assert report["summary"]["e2e_query_input_record_count"] == 5
    assert report["summary"]["answer_permission_count"] == 0
    assert report["schema_missing_required_key_record_count"] == 0


def test_read_queries_from_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "queries.jsonl"
    p.write_text('{"query":"Find part number 120-36833-001"}\n{"user_query":"Find IPL item 130"}\n', encoding="utf-8")
    assert read_queries_from_file(p) == ["Find part number 120-36833-001", "Find IPL item 130"]


def test_build_script_round_trip(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    cmd = [
        sys.executable,
        "scripts/build/ingestion/build_trace_net_e2e_query_input_v1.py",
        "--include-standard-demo-queries",
        "--output-dir",
        str(output_dir),
        "--min-query-records",
        "5",
        "--min-routeable-queries",
        "5",
        "--min-unique-intents",
        "4",
        "--min-planned-retrieval-queries",
        "5",
        "--require-no-answer-permission",
        "--quality",
    ]
    subprocess.run(cmd, check=True)
    report = json.loads((output_dir / "trace_net_e2e_query_input_v1.json").read_text(encoding="utf-8"))
    assert report["quality_status"] == QUALITY_PASS
    assert len(report["query_records"]) == 5


def test_quality_script_round_trip(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    subprocess.run(
        [
            sys.executable,
            "scripts/build/ingestion/build_trace_net_e2e_query_input_v1.py",
            "--include-standard-demo-queries",
            "--output-dir",
            str(output_dir),
            "--min-query-records",
            "5",
            "--min-routeable-queries",
            "5",
            "--min-unique-intents",
            "4",
            "--min-planned-retrieval-queries",
            "5",
            "--require-no-answer-permission",
            "--quality",
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/maintenance/validation/check_trace_net_e2e_query_input_v1_quality.py",
            "--report-path",
            str(output_dir / "trace_net_e2e_query_input_v1.json"),
            "--min-query-records",
            "5",
            "--min-routeable-queries",
            "5",
            "--min-unique-intents",
            "4",
            "--min-planned-retrieval-queries",
            "5",
            "--require-no-answer-permission",
            "--write-json",
        ],
        check=True,
    )
