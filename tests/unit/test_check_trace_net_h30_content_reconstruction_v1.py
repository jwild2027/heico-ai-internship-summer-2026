from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/maintenance/writing/check_trace_net_h30_content_reconstruction_v1.py")


def load(name="phase3_checker"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write_record(path: Path, qid: str, route: str, telemetry: dict):
    payload = {
        "evaluation": {
            "question_id": qid,
            "post_validation_accepted": True,
        },
        "raw_response": {
            "trace_net": {
                "route": route,
                "answer_mode": {"typed_record_source": "claim_ready_evidence"},
                "content_reconstruction": {
                    "quality_status": "PASS",
                    "final_validation_accepted": True,
                    "source_truth_mutation_allowed": False,
                    **telemetry,
                },
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_checker_accepts_phase3_target_records(tmp_path):
    mod = load("phase3_checker_pass")
    write_record(tmp_path / "10_q10_ata.json", "q10", "ata_system_discovery", {"ata_page_role_count": 3})
    write_record(tmp_path / "12_q12_table.json", "q12", "exact_table_ipl_lookup", {"table_part_page_match": True})
    write_record(tmp_path / "16_q16_proc.json", "q16", "procedure_task_lookup", {"procedure_step_count": 6, "procedure_sequence_count": 2})
    write_record(tmp_path / "14_q14_visual.json", "q14", "visual_figure_callout_lookup", {"visual_callout_claim_added": False, "visual_resolved_callout_count": 0})
    report = mod.inspect_run(tmp_path)
    assert report["quality_status"] == "PASS", report
    assert report["passed_record_count"] == 4


def test_checker_rejects_missing_typed_source_and_sequence(tmp_path):
    mod = load("phase3_checker_fail")
    payload = {
        "evaluation": {"question_id": "q16", "post_validation_accepted": True},
        "raw_response": {
            "trace_net": {
                "route": "procedure_task_lookup",
                "answer_mode": {"mode": "exact_page_content"},
                "content_reconstruction": {
                    "quality_status": "PASS",
                    "source_truth_mutation_allowed": False,
                    "procedure_step_count": 4,
                    "procedure_sequence_count": 1,
                },
            }
        },
    }
    (tmp_path / "16_q16_proc.json").write_text(json.dumps(payload), encoding="utf-8")
    report = mod.inspect_run(tmp_path)
    assert report["quality_status"] == "FAIL"
    failures = report["results"][0]["failures"]
    assert "answer_mode_missing_typed_record_source" in failures
    assert "procedure_sequence_reset_not_detected" in failures
