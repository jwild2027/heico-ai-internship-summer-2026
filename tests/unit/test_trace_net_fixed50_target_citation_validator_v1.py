import json
from pathlib import Path

from scripts.validate_trace_net_fixed50_target_citation_v1 import (
    citation_matches_target,
    extract_part_targets,
    main,
    normalize_for_match,
    selected_citations,
    summarize,
    validate_record,
)


def test_normalize_for_match_removes_punctuation_and_case():
    assert normalize_for_match("df 250040-501") == "DF250040501"
    assert normalize_for_match("120-36833-001") == "12036833001"


def test_extract_part_targets_finds_alpha_and_numeric_parts():
    targets = extract_part_targets("Find DF250040-501 and 120-36833-001")
    norms = {t["target_norm"] for t in targets}
    assert "DF250040501" in norms
    assert "12036833001" in norms


def test_citation_matches_explicit_target_value():
    citation = {"field_name": "covered_part_number", "normalized_value": "120-36833-001"}
    assert citation_matches_target(citation, ["12036833001"])
    assert not citation_matches_target(citation, ["DF250040501"])


def test_selected_citations_reads_selected_trace_try_and_dedupes():
    record = {
        "selected_query_variant": "DF250040-501",
        "trace_tries": [
            {"query_variant": "wrong", "citation_count": 1, "trace_response": {"citations": [{"normalized_value": "AAA"}]}},
            {
                "query_variant": "DF250040-501",
                "citation_count": 1,
                "trace_response": {
                    "citations": [{"normalized_value": "DF250040-501"}],
                    "response": {"citations": [{"normalized_value": "DF250040-501"}]},
                },
            },
        ],
    }
    citations = selected_citations(record)
    assert len(citations) == 1
    assert citations[0]["normalized_value"] == "DF250040-501"


def test_validate_record_flags_off_target_citation_but_safe_no_proof():
    record = {
        "question_id": "q03",
        "question": "Find part number DF250040-501.",
        "answer": "The part number DF250040-501 was not found. Source-trace status: Not source-trace-ready.",
        "citation_count": 6,
        "selected_query_variant": "Find part number DF250040-501.",
        "trace_tries": [
            {
                "query_variant": "Find part number DF250040-501.",
                "citation_count": 6,
                "trace_response": {
                    "citations": [
                        {"field_name": "covered_part_number", "normalized_value": "120-36833-001"},
                        {"field_name": "covered_part_number", "normalized_value": "120-36833-003"},
                    ]
                },
            }
        ],
        "grade": {"source_trace_ready_claim": False, "engram_policy_used_as_source_proof": False},
    }
    result = validate_record(record, ["DF250040501"])
    assert result.off_target_citation_returned is True
    assert result.safe_no_proof_answer is True
    assert result.corpus_missing_target is True
    assert result.target_citation_backed is False
    assert result.unsupported_claim is False


def test_validate_record_accepts_target_matching_citation():
    record = {
        "question_id": "q02",
        "question": "What is the part number 120-36833-001?",
        "answer": "The evidence contains part number 120-36833-001.",
        "citation_count": 1,
        "citations": [{"field_name": "covered_part_number", "normalized_value": "120-36833-001"}],
        "grade": {"source_trace_ready_claim": False, "engram_policy_used_as_source_proof": False},
    }
    result = validate_record(record, [])
    assert result.target_citation_backed is True
    assert result.target_citation_count == 1
    assert result.off_target_citation_returned is False


def test_summarize_adjusts_raw_citation_count_for_off_target_citations():
    rows = [
        {
            "question_id": "q02",
            "question": "What is the part number 120-36833-001?",
            "answer": "The evidence contains part number 120-36833-001.",
            "citation_count": 1,
            "citations": [{"normalized_value": "120-36833-001"}],
        },
        {
            "question_id": "q03",
            "question": "Find part number DF250040-501.",
            "answer": "DF250040-501 was not found. Not source-trace-ready.",
            "citation_count": 1,
            "citations": [{"normalized_value": "120-36833-001"}],
        },
    ]
    validations = [validate_record(row, ["DF250040501"]) for row in rows]
    summary = summarize(validations, rows, ["DF250040-501"])
    assert summary["raw_citation_backed_count"] == 2
    assert summary["adjusted_citation_backed_count"] == 1
    assert summary["target_citation_backed_count"] == 1
    assert summary["off_target_citation_answer_count"] == 1
    assert summary["quality_status"] == "PASS"
    assert summary["target_quality_status"] == "WARN"


def test_cli_writes_summary_and_records(tmp_path: Path):
    answers = tmp_path / "answers.jsonl"
    answers.write_text(
        json.dumps(
            {
                "question_id": "q03",
                "question": "Find part number DF250040-501.",
                "answer": "DF250040-501 was not found. Not source-trace-ready.",
                "citation_count": 1,
                "citations": [{"normalized_value": "120-36833-001"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary = tmp_path / "summary.json"
    records = tmp_path / "records.jsonl"
    rc = main(
        [
            "--answers",
            str(answers),
            "--summary-output",
            str(summary),
            "--records-output",
            str(records),
            "--corpus-missing-target",
            "DF250040-501",
        ]
    )
    assert rc == 0
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["off_target_citation_answer_count"] == 1
    assert data["corpus_missing_answer_count"] == 1
    assert records.exists()
