import json
from pathlib import Path

from tiff.trace_net_engineering_runner_eval_set_v1 import (
    build_engineering_runner_eval_set,
    check_engineering_runner_eval_set,
)


def _touch_inputs(tmp_path):
    paths = {}
    for name in [
        "v2_summary_guidance_index",
        "image_visual_evidence_pack",
        "raw_ocr_nomenclature_extractor",
        "table_route_evidence_packager",
        "table_exact_search_adapter",
    ]:
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
        paths[name] = p
    return paths


def _passing_runner(**kwargs):
    q = kwargs["question"]
    return {
        "status": "TRACE_NET_ENGINEERING_ANSWER_RUNNER_BUILT",
        "quality_status": "PASS",
        "answer_text": f"Answer for {q} [V6] [O1]",
        "stage_reports": {"engineering_query_planner": "planner.json"},
        "summary": {
            "task_type": "visual_part_identification",
            "stage_pass_count": 3,
            "proof_context_count": 3,
            "answer_citation_count": 2,
            "valid_answer_citation_count": 2,
            "source_trace_ready_citation_count": 2,
            "ready_for_engineering_answer_delivery": True,
            "summary_used_as_proof_count": 0,
            "unsupported_claim_count": 0,
            "invalid_answer_citation_count": 0,
            "llava_only_part_identity_claim_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "unsafe_record_count": 0,
        },
    }


def test_eval_set_passes_with_fake_runner(tmp_path):
    inputs = _touch_inputs(tmp_path)
    manifest = build_engineering_runner_eval_set(
        questions=["What does figure 69 show?", "What does figure 75 show?"],
        output_dir=tmp_path / "eval",
        runner_builder=_passing_runner,
        min_eval_questions=2,
        min_runner_passes=2,
        require_quality_pass=True,
        **inputs,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["eval_question_count"] == 2
    assert manifest["summary"]["runner_pass_count"] == 2
    assert (tmp_path / "eval" / "trace_net_engineering_runner_eval_set_v1_records.csv").exists()


def test_eval_set_records_runner_errors_without_crashing(tmp_path):
    inputs = _touch_inputs(tmp_path)

    def bad_runner(**kwargs):
        raise RuntimeError("boom")

    manifest = build_engineering_runner_eval_set(
        questions=["Bad question"],
        output_dir=tmp_path / "eval",
        runner_builder=bad_runner,
        min_eval_questions=1,
        min_runner_passes=0,
        **inputs,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["records"][0]["runner_passed"] is False
    assert "RuntimeError" in manifest["records"][0]["error"]


def test_eval_set_fails_when_runner_pass_threshold_not_met(tmp_path):
    inputs = _touch_inputs(tmp_path)
    manifest = build_engineering_runner_eval_set(
        questions=["Bad question"],
        output_dir=tmp_path / "eval",
        runner_builder=lambda **kwargs: {"quality_status": "FAIL", "summary": {}},
        min_eval_questions=1,
        min_runner_passes=1,
        **inputs,
    )
    assert manifest["quality_status"] == "FAIL"
    assert any("runner_pass_count below minimum" in f for f in manifest["failures"])


def test_check_eval_set_enforces_quality(tmp_path):
    inputs = _touch_inputs(tmp_path)
    manifest = build_engineering_runner_eval_set(
        questions=["What does figure 69 show?"],
        output_dir=tmp_path / "eval",
        runner_builder=_passing_runner,
        min_eval_questions=1,
        min_runner_passes=1,
        **inputs,
    )
    report = check_engineering_runner_eval_set(
        eval_set=tmp_path / "eval" / "trace_net_engineering_runner_eval_set_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        min_eval_questions=1,
        min_runner_passes=1,
    )
    assert report["quality_status"] == "PASS"
    assert (tmp_path / "check.json").exists()


def test_eval_set_classifies_missing_stage_quality_check(tmp_path):
    inputs = _touch_inputs(tmp_path)

    def missing_quality_check_runner(**kwargs):
        raise FileNotFoundError(
            "local_data/organization/trace_net/eval/runs/q04/context_pack/"
            "trace_net_engineering_answer_context_pack_v1_quality_check.json"
        )

    manifest = build_engineering_runner_eval_set(
        questions=["Find part number 120-50645-005 and cite the source."],
        output_dir=tmp_path / "eval",
        runner_builder=missing_quality_check_runner,
        min_eval_questions=1,
        min_runner_passes=0,
        **inputs,
    )
    record = manifest["records"][0]
    assert manifest["quality_status"] == "PASS"
    assert record["runner_passed"] is False
    assert record["failed_stage"] == "engineering_answer_context_pack"
    assert record["failure_type"] == "missing_stage_quality_check"
    assert "did not produce the expected quality-check artifact" in record["failure_reason"]
    assert manifest["summary"]["runner_plumbing_failure_count"] == 1
    assert manifest["summary"]["missing_stage_quality_check_count"] == 1
