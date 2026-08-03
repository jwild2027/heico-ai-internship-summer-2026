import json

from scripts.check_trace_net_h30_constrained_gemma_writer_v1 import inspect_run


def _write(path, qid, route, writer, accepted=True):
    if writer.get("structured_output_accepted"):
        effective = "constrained_gemma_structured_output_validated"
    elif writer.get("reason") == "insufficient_remaining_budget":
        effective = "phase3_deterministic_fallback_before_constrained_gemma_budget_exhaustion"
    elif writer.get("reason") == "gemma_call_timeout":
        effective = "phase3_deterministic_fallback_after_constrained_gemma_timeout"
    else:
        effective = "phase3_deterministic_fallback_after_constrained_output_rejection"
    payload = {
        "evaluation": {"question_id": qid, "post_validation_accepted": accepted},
        "raw_response": {"trace_net": {
            "route": route,
            "writer_mode": "public_answer_contract_v1",
            "writer_mode_before_public_answer_contract": effective,
            "post_answer_validation": {"accepted": accepted},
            "constrained_gemma_writer": writer,
        }},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _packet():
    return {
        "schema_version": "trace_net_constrained_writer_packet_v1",
        "question": "Find part 120-1",
        "route": "exact_identifier_lookup",
        "deterministic_sections": {"answer": ["a"], "evidence": ["e [1]"], "limits": []},
    }


def test_checker_accepts_one_call_budget_skip_and_safe_route_skip(tmp_path):
    _write(tmp_path / "01_q01.json", "q01", "exact_identifier_lookup", {
        "single_call_maximum": True,
        "legacy_freeform_gemma_suppressed": True,
        "eligible": True,
        "call_attempted": True,
        "call_count": 1,
        "structured_output_accepted": True,
        "phase3_fallback_used": False,
        "reason": "structured_output_validated",
        "packet": _packet(),
        "packet_validation": {"quality_status": "PASS"},
        "overall_budget_seconds": 210,
        "total_elapsed_ms": 100000,
    })
    _write(tmp_path / "02_q02.json", "q02", "ata_system_discovery", {
        "single_call_maximum": True,
        "legacy_freeform_gemma_suppressed": True,
        "eligible": True,
        "call_attempted": False,
        "call_count": 0,
        "structured_output_accepted": False,
        "phase3_fallback_used": True,
        "reason": "insufficient_remaining_budget",
        "overall_budget_seconds": 210,
        "total_elapsed_ms": 195000,
    })
    _write(tmp_path / "03_q03.json", "q03", "visual_figure_callout_lookup", {
        "single_call_maximum": True,
        "legacy_freeform_gemma_suppressed": True,
        "eligible": False,
        "call_attempted": False,
        "call_count": 0,
        "structured_output_accepted": False,
        "phase3_fallback_used": False,
        "reason": "route_not_in_canary",
        "overall_budget_seconds": 210,
        "total_elapsed_ms": 50000,
    })
    report = inspect_run(tmp_path)
    assert report["quality_status"] == "PASS", report
    assert report["gemma_call_count"] == 1
    assert report["budget_skip_count"] == 1
    assert report["maximum_calls_per_record"] == 1


def test_checker_accepts_timeout_with_validated_fallback(tmp_path):
    _write(tmp_path / "01_q01.json", "q01", "exact_table_ipl_lookup", {
        "single_call_maximum": True,
        "legacy_freeform_gemma_suppressed": True,
        "eligible": True,
        "call_attempted": True,
        "call_count": 1,
        "structured_output_accepted": False,
        "phase3_fallback_used": True,
        "reason": "gemma_call_timeout",
        "model_call_timed_out": True,
        "overall_budget_seconds": 210,
        "total_elapsed_ms": 150000,
    })
    _write(tmp_path / "02_q02.json", "q02", "exact_identifier_lookup", {
        "single_call_maximum": True,
        "legacy_freeform_gemma_suppressed": True,
        "eligible": True,
        "call_attempted": True,
        "call_count": 1,
        "structured_output_accepted": True,
        "phase3_fallback_used": False,
        "reason": "structured_output_validated",
        "packet": _packet(),
        "packet_validation": {"quality_status": "PASS"},
        "overall_budget_seconds": 210,
        "total_elapsed_ms": 100000,
    })
    report = inspect_run(tmp_path)
    assert report["quality_status"] == "PASS", report
    assert report["model_timeout_fallback_count"] == 1


def test_checker_rejects_second_call_and_packet_leak(tmp_path):
    _write(tmp_path / "01_q01.json", "q01", "exact_identifier_lookup", {
        "single_call_maximum": True,
        "legacy_freeform_gemma_suppressed": True,
        "eligible": True,
        "call_attempted": True,
        "call_count": 2,
        "structured_output_accepted": False,
        "phase3_fallback_used": True,
        "reason": "bad",
        "packet": {"evidence_envelope": {}},
        "packet_validation": {"quality_status": "FAIL"},
        "overall_budget_seconds": 210,
        "total_elapsed_ms": 1000,
    })
    report = inspect_run(tmp_path)
    assert report["quality_status"] == "FAIL"
    assert report["second_call_violation_count"] == 1
    assert report["packet_leak_count"] == 1


def test_checker_detects_incomplete_live_run(tmp_path):
    _write(tmp_path / "01_q01.json", "q01", "exact_identifier_lookup", {
        "single_call_maximum": True,
        "legacy_freeform_gemma_suppressed": True,
        "eligible": True,
        "call_attempted": True,
        "call_count": 1,
        "structured_output_accepted": True,
        "phase3_fallback_used": False,
        "reason": "structured_output_validated",
        "packet": _packet(),
        "packet_validation": {"quality_status": "PASS"},
        "overall_budget_seconds": 210,
        "total_elapsed_ms": 1000,
    })
    report = inspect_run(tmp_path, expected_record_count=20)
    assert report["quality_status"] == "FAIL"
    assert report["failure_counts"]["incomplete_run"] == 1
