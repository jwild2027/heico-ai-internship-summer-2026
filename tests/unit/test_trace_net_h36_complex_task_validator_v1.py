import json
from pathlib import Path

from tiff.trace_net_h36_complex_task_validator_v1 import (
    build_complex_task_validator,
    check_complex_task_validator,
    negation_aware_forbidden_findings,
    validate_record,
)


def test_negated_forbidden_claim_is_safe():
    unsafe, safe = negation_aware_forbidden_findings(
        "TRACE-Net does not verify interchangeability, approved replacement status, or installation safety."
    )
    assert unsafe == []
    assert any("interchange" in x for x in safe)
    assert any("installation safety" in x for x in safe)


def test_positive_forbidden_claim_is_unsafe():
    unsafe, safe = negation_aware_forbidden_findings(
        "This proves interchangeability and installation safety."
    )
    assert "possible_forbidden_claim:interchangeability" in unsafe
    assert "possible_forbidden_claim:installation safety" in unsafe


def test_quiz_contract_rejects_internal_metadata():
    rec = {
        "question_id": "q",
        "task_type": "quiz_generation",
        "grade": "GOOD",
        "fallback_used": False,
        "selected_routes": ["visual", "ocr"],
        "selected_evidence_labels": ["V1", "O2", "V3", "O4"],
        "answer_char_count": 500,
        "answer_preview": """Technician Quiz
1. What is A?\n2. What is B?\n3. What is C?\n4. Does this prove interchangeability?\n5. Which evidence label supports a source_extractor_quality_pass?\nAnswer Key\n1. A [V1]\n2. B [O2]\n3. C [V3]\n4. No, it does not prove interchangeability [O4]\n5. [V1]\n""",
    }
    out = validate_record(rec)
    assert "metadata_quiz_item:source_extractor_quality_pass" in out["findings"]
    assert out["h36_grade"] == "PARTIAL"


def test_build_and_check(tmp_path):
    src = tmp_path / "h35.json"
    data = {
        "quality_status": "PASS",
        "summary": {"write_attempt_count": 0},
        "records": [
            {
                "question_id": "q02",
                "task_type": "representative_page_explanation",
                "grade": "BAD",
                "fallback_used": False,
                "selected_routes": ["visual"],
                "selected_evidence_labels": ["V21", "V22"],
                "answer_char_count": 341,
                "answer_preview": "Answer: Page 382 identifies part 120-29068-003 [V21] [V22]. Evidence: [V21] [V22]. Engineering confidence: High. Limits: TRACE-Net does not verify interchangeability, approved replacement status, or installation safety.",
            },
            {
                "question_id": "q04",
                "task_type": "nomenclature_lookup",
                "grade": "GOOD",
                "fallback_used": False,
                "selected_routes": ["ocr", "visual"],
                "selected_evidence_labels": ["O10", "V17"],
                "answer_char_count": 400,
                "answer_preview": "Answer: The nomenclature is X [O10]. Evidence: [O10] [V17]. Engineering confidence: High. Limits: Does not prove installation safety.",
            },
        ],
    }
    src.write_text(json.dumps(data), encoding="utf-8")
    result = build_complex_task_validator(src, tmp_path / "out", min_records=2, min_contract_pass=2, max_bad=0, max_fallback_used=0, require_source_quality_pass=True, require_no_answer_permission=True)
    assert result["quality_status"] == "PASS"
    assert result["summary"]["contract_pass_count"] == 2
    checked = check_complex_task_validator(tmp_path / "out" / "trace_net_h36_complex_task_validator_v1.json", min_records=2, min_contract_pass=2, require_quality_pass=True)
    assert checked["quality_status"] == "PASS"
