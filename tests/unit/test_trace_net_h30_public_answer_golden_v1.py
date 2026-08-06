from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/benchmark/writing/check_trace_net_h30_public_answer_golden_v1.py")
CONTRACT_PATH = Path("tests/fixtures/trace_net_h30_tiff_grounded20_public_answer_golden_v1.json")


def load(name="trace_net_h30_public_answer_golden_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_golden_contract_has_all_20_stable_questions():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    questions = contract["questions"]
    assert len(questions) == 20
    assert [row["question_id"] for row in questions] == [f"q{i:02d}" for i in range(1, 21)]
    assert len({row["question"] for row in questions}) == 20
    assert contract["global"]["required_headings"] == ["## Answer", "## Evidence"]


def test_checker_accepts_clean_subset_and_reports_metrics():
    mod = load("golden_checker_clean")
    contract = {
        "contract_id": "small",
        "global": {
            "required_headings": ["## Answer", "## Evidence"],
            "allowed_headings": ["## Answer", "## Evidence", "## Limits"],
            "require_post_validation_accepted": True,
            "forbidden_text": ["embedding_candidate:"],
            "raw_internal_labels": ["embedding_candidate:"],
        },
        "questions": [
            {
                "question_id": "q01",
                "category": "exact_part",
                "question": "Find part 120-20970-001.",
                "required_text": ["120-20970-001", "t_p_120_1176_p000343"],
                "required_headings": ["## Answer", "## Evidence", "## Limits"],
                "require_limits": True,
                "require_answer_citation": True,
            }
        ],
    }
    summary = {
        "records": [
            {
                "question_id": "q01",
                "category": "exact_part",
                "question": "Find part 120-20970-001.",
                "post_validation_accepted": True,
                "answer": (
                    "## Answer\n\nThe best indexed match for `120-20970-001` is shown below [1].\n\n"
                    "## Evidence\n\n- `120-20970-001` — page `t_p_120_1176_p000343` [1]\n\n"
                    "## Limits\n\n- The record remains a candidate."
                ),
            }
        ]
    }
    report = mod.validate_contract(summary, contract)
    assert report["quality_status"] == "PASS", report
    assert report["passed_question_count"] == 1
    assert report["unrelated_nomenclature_result_count"] == 0
    assert report["raw_internal_label_count"] == 0


def test_checker_detects_unrelated_nomenclature_and_rejected_validation():
    mod = load("golden_checker_bad")
    contract = {
        "contract_id": "small",
        "global": {
            "required_headings": ["## Answer", "## Evidence"],
            "allowed_headings": ["## Answer", "## Evidence", "## Limits"],
            "require_post_validation_accepted": True,
            "forbidden_text": [],
            "raw_internal_labels": [],
        },
        "questions": [
            {
                "question_id": "q08",
                "category": "nomenclature",
                "question": "Find the ring in the document set.",
                "required_text": ["120-48024-001"],
                "required_headings": ["## Answer", "## Evidence", "## Limits"],
                "require_limits": True,
                "forbidden_identifiers": ["120-29068-025"],
            }
        ],
    }
    summary = {
        "records": [
            {
                "question_id": "q08",
                "category": "nomenclature",
                "question": "Find the ring in the document set.",
                "post_validation_accepted": False,
                "answer": (
                    "## Answer\n\nMatches are below.\n\n## Evidence\n\n"
                    "- `120-48024-001` — Ring Locking [1]\n"
                    "- `120-29068-025` — unrelated [2]\n\n"
                    "## Limits\n\n- Guidance only."
                ),
            }
        ]
    }
    report = mod.validate_contract(summary, contract)
    assert report["quality_status"] == "FAIL"
    assert report["unrelated_nomenclature_result_count"] == 1
    assert report["post_validation_rejected_count"] == 1
