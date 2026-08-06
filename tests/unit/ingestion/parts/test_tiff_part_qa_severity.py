from __future__ import annotations

from tiff.part_qa_severity import (
    looks_like_ata_reference,
    looks_like_compound_part_reference,
    looks_like_plausible_part,
    summarize_triage,
    terminal_row_summary,
    triage_row,
    triage_rows,
)


def test_ata_reference_is_info_not_review() -> None:
    row = {
        "check": "suspicious_part_ata",
        "severity": "review",
        "part_number": "25-21-00-46",
        "message": "Looks like ATA",
    }
    decision = triage_row(row)
    assert decision.severity == "info"
    assert decision.category == "non_part_ata_reference"
    assert decision.action == "suppress_from_review_queue"
    assert not decision.needs_review


def test_known_ocr_document_token_is_info() -> None:
    row = {
        "check": "parts_missing_nomenclature",
        "severity": "review",
        "part_number": "IGURE",
        "message": "No nomenclature found",
    }
    decision = triage_row(row)
    assert decision.severity == "info"
    assert decision.category == "ocr_or_document_noise"


def test_figure_or_sheet_reference_is_info() -> None:
    row = {"severity": "review", "part_number": "00-08A"}
    decision = triage_row(row)
    assert decision.severity == "info"
    assert decision.category == "non_part_figure_or_sheet_reference"
    assert decision.action == "suppress_from_review_queue"
    assert not looks_like_plausible_part("00-08A")


def test_slash_code_without_part_group_shape_is_info() -> None:
    row = {"severity": "review", "part_number": "E0/5221"}
    decision = triage_row(row)
    assert decision.severity == "info"
    assert decision.category == "non_part_slash_reference"
    assert decision.action == "suppress_from_review_queue"
    assert not looks_like_plausible_part("E0/5221")


def test_compound_part_reference_is_info_not_noise() -> None:
    row = {
        "check": "part_nomenclature_conflicts",
        "severity": "review",
        "part_number": "120-29067-019/029",
    }
    decision = triage_row(row)
    assert decision.severity == "info"
    assert decision.category == "compound_part_reference"
    assert decision.action == "keep_as_info"
    assert looks_like_compound_part_reference("120-29068-017/027/039/059")


def test_real_part_conflict_stays_review() -> None:
    row = {
        "check": "part_nomenclature_conflicts",
        "severity": "review",
        "part_number": "120-37313-001",
        "nomenclature": "HOLDER, MAGAZINE / HOLDER MAGAZINE",
    }
    decision = triage_row(row)
    assert decision.severity == "review"
    assert decision.category == "real_part_nomenclature_conflict"
    assert decision.needs_review


def test_real_alpha_numeric_part_missing_nomenclature_stays_review() -> None:
    row = {"check": "parts_missing_nomenclature", "severity": "review", "part_number": "AM03078-22"}
    decision = triage_row(row)
    assert decision.severity == "review"
    assert decision.category == "real_part_missing_nomenclature"
    assert decision.needs_review


def test_plausible_part_without_specific_issue_gets_named_review_category() -> None:
    row = {"severity": "review", "part_number": "120-26948-001", "check": "-"}
    decision = triage_row(row)
    assert decision.severity == "review"
    assert decision.category == "real_part_catalog_review"
    assert decision.action == "manual_review"


def test_nomenclature_groups_are_info_by_default() -> None:
    row = {"check": "nomenclature_groups", "severity": "review", "nomenclature": "HOLDER, MAGAZINE", "count": "3"}
    decision = triage_row(row)
    assert decision.severity == "info"
    assert decision.category == "informational_nomenclature_group"


def test_triage_rows_preserves_original_severity_and_updates_summary() -> None:
    rows = triage_rows(
        [
            {"check": "suspicious_part_ata", "severity": "review", "part_number": "25-21-00-46"},
            {"check": "part_nomenclature_conflicts", "severity": "review", "part_number": "120-37313-001"},
            {"check": "inventory", "severity": "ok", "part_number": "120-37313-001"},
        ]
    )
    summary = summarize_triage(rows)
    assert rows[0]["original_severity"] == "review"
    assert rows[0]["severity"] == "info"
    assert rows[1]["severity"] == "review"
    assert rows[2]["severity"] == "ok"
    assert summary["by_severity"] == {"info": 1, "ok": 1, "review": 1}
    assert summary["review_queue_rows"] == 1
    assert summary["suppressed_from_review_queue"] == 1


def test_part_shape_helpers() -> None:
    assert looks_like_ata_reference("25-21-00-105")
    assert not looks_like_plausible_part("25-21-00-105")
    assert looks_like_plausible_part("120-37313-001")
    assert looks_like_plausible_part("AM03078-22")


def test_write_triage_outputs_writes_csv_json_not_html(tmp_path) -> None:
    from tiff.part_qa_severity import write_triage_outputs

    rows = triage_rows([
        {"check": "suspicious_part_ata", "severity": "review", "part_number": "25-21-00-46"},
    ])
    outputs = write_triage_outputs(rows, tmp_path / "qa_triaged")
    assert set(outputs) == {"csv", "json"}
    assert (tmp_path / "qa_triaged.csv").exists()
    assert (tmp_path / "qa_triaged.json").exists()
    assert not (tmp_path / "qa_triaged.html").exists()


def test_terminal_row_summary_includes_key_fields() -> None:
    rows = triage_rows([
        {"check": "part_nomenclature_conflicts", "severity": "review", "part_number": "120-37313-001"},
    ])
    text = terminal_row_summary(rows[0])
    assert "severity=review" in text
    assert "part=120-37313-001" in text
    assert "category=real_part_nomenclature_conflict" in text
