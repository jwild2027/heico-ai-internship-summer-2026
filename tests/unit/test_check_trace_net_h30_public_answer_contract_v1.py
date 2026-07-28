from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/check_trace_net_h30_public_answer_contract_v1.py")


def load(name="check_trace_net_h30_public_answer_contract_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_summary_checker_passes_clean_records():
    mod = load("contract_checker_pass")
    payload = {
        "records": [
            {
                "question_id": "q01",
                "actual_route": "exact_identifier_lookup",
                "answer": "## Answer\n\nPart `120-20970-003` appears [1].\n\n## Evidence\n\n- Page `t_p_x_p000001` [1]",
                "post_validation_accepted": True,
            },
            {
                "question_id": "q20",
                "actual_route": "document_page_navigation",
                "answer": "## Answer\n\nPage `t_p_x_p999999` was not found.\n\n## Evidence\n\n- No matching indexed page record was returned.",
                "post_validation_accepted": True,
            },
        ]
    }
    report = mod.validate_summary(payload)
    assert report["quality_status"] == "PASS"
    assert report["passed_question_count"] == 2
    assert report["public_leak_count"] == 0


def test_summary_checker_fails_internal_leak_or_rejected_validation():
    mod = load("contract_checker_fail")
    payload = {
        "records": [
            {
                "question_id": "q01",
                "actual_route": "exact_identifier_lookup",
                "answer": "## Answer\n\nResult.\n\n## Evidence\n\n- embedding_candidate: raw",
                "post_validation_accepted": False,
            }
        ]
    }
    report = mod.validate_summary(payload)
    assert report["quality_status"] == "FAIL"
    assert report["failed_question_count"] == 1
    assert report["public_leak_count"] >= 1
    assert report["post_validation_rejected_count"] == 1
