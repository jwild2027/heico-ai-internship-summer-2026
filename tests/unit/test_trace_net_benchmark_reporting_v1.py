import csv
import json
from pathlib import Path

from scripts.benchmark.trace_net_benchmark_reporting_v1 import (
    build_progress_summary,
    completed_question_ids,
    load_records_jsonl,
    write_qa_reports,
)


def sample_records():
    long_answer = "FULL ANSWER " + ("evidence and explanation " * 30)
    return [
        {
            "question_id": "q001",
            "category": "partial_part_prefix",
            "query": "I only know the part starts with 123",
            "quality_status": "PASS",
            "expected_route": "guided_part_discovery",
            "actual_route": "guided_part_discovery",
            "planned_tunnels": ["part_prefix"],
            "used_tunnels": ["part_prefix"],
            "answer": long_answer,
            "writer_status": "SKIPPED_NO_DIRECT_EVIDENCE",
            "citation_count": 0,
            "direct_evidence_count": 0,
            "candidate_evidence_count": 2,
            "follow_up_questions": ["Do you remember more digits?"],
            "latency_ms": 1000,
            "failures": [],
        },
        {
            "question_id": "q002",
            "category": "exact_part_lookup",
            "query": "Find part 120-1",
            "quality_status": "FAIL",
            "expected_route": "exact_identifier_lookup",
            "actual_route": "exact_identifier_lookup",
            "planned_tunnels": ["exact_identifier"],
            "used_tunnels": ["other"],
            "answer": "A complete failed answer.",
            "writer_status": "SKIPPED_NO_DIRECT_EVIDENCE",
            "citation_count": 0,
            "direct_evidence_count": 0,
            "candidate_evidence_count": 1,
            "follow_up_questions": [],
            "latency_ms": 2000,
            "failures": ["used_tunnel_not_planned"],
        },
    ]


def test_load_records_tolerates_only_trailing_partial_line(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    path.write_text(
        json.dumps(sample_records()[0]) + "\n" + '{"question_id": "q002"',
        encoding="utf-8",
    )
    rows, warnings = load_records_jsonl(path)
    assert len(rows) == 1
    assert warnings and warnings[0].startswith("ignored_trailing_partial_json_line")


def test_complete_question_ids_are_stable():
    assert completed_question_ids(sample_records()) == ["q001", "q002"]


def test_reports_keep_full_answer_and_failed_only_output(tmp_path: Path):
    outputs = write_qa_reports(
        sample_records(),
        output_dir=tmp_path,
        expected_question_count=180,
        interrupted=True,
    )
    full_md = Path(outputs["full_question_answers_markdown"]).read_text(encoding="utf-8")
    failed_md = Path(outputs["failed_question_answers_markdown"]).read_text(encoding="utf-8")
    assert "evidence and explanation" in full_md
    assert len(full_md) > 180
    assert "Q002" in failed_md
    assert "Q001" not in failed_md

    with Path(outputs["full_question_answers_csv"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["answer"].startswith("FULL ANSWER")

    progress = json.loads(Path(outputs["progress_summary"]).read_text(encoding="utf-8"))
    assert progress["status"] == "INTERRUPTED"
    assert progress["question_count"] == 2
    assert progress["pass_count"] == 1
    assert progress["fail_count"] == 1


def test_progress_summary_complete_pass():
    rows = sample_records()[:1]
    summary = build_progress_summary(
        rows,
        expected_question_count=1,
        interrupted=False,
        load_warnings=[],
        run_metadata={"git_commit": "abc"},
    )
    assert summary["status"] == "COMPLETE"
    assert summary["quality_status"] == "PASS"
