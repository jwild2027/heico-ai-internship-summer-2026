import json
from pathlib import Path

from tiff.trace_net_engineering_semantic_answer_quality_eval_v1 import (
    build_semantic_answer_quality_eval,
    check_semantic_answer_quality_eval,
)


def _composer(path: Path, question: str, intent: str, answer: str):
    data = {
        "quality_status": "PASS",
        "answer_text": answer,
        "summary": {
            "question": question,
            "task_type": "exact_part_lookup",
            "intent_answer_type": intent,
            "answer_citation_count": answer.count("["),
            "valid_answer_citation_count": answer.count("["),
            "source_trace_ready_citation_count": max(2, answer.count("[")),
            "invalid_answer_citation_count": 0,
            "unsupported_claim_count": 0,
            "summary_used_as_proof_count": 0,
            "llava_only_part_identity_claim_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "unsafe_record_count": 0,
        },
        "quality_gate": {"quality_status": "PASS"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_interchangeability_semantic_pass(tmp_path):
    p = _composer(
        tmp_path / "c" / "trace_net_engineering_intent_answer_composer_v1.json",
        "Is 120-50645-005 interchangeable with 120-50645-011?",
        "unsupported_interchangeability",
        "TRACE-Net cannot prove that 120-50645-005 and 120-50645-011 are interchangeable. "
        "Both have DOUBLE PASSENGER SEAT ASSY evidence [V6] [O1], but same nomenclature is not approval. "
        "Interchangeability would require explicit effectivity, supersedure, replacement, or approved source documentation.",
    )
    manifest = build_semantic_answer_quality_eval(
        composer=[p],
        output_dir=tmp_path / "out",
        min_semantic_records=1,
        min_semantic_passes=1,
        max_semantic_failures=0,
        require_quality_pass=True,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["semantic_pass_count"] == 1


def test_installation_safety_semantic_pass(tmp_path):
    p = _composer(
        tmp_path / "c" / "trace_net_engineering_intent_answer_composer_v1.json",
        "Does figure 69 prove installation safety?",
        "unsupported_installation_safety",
        "No. Figure 69 does not prove installation safety [V6] [O1]. It identifies the figure-linked part, "
        "but installation safety requires approved procedure, effectivity, and safety evidence.",
    )
    manifest = build_semantic_answer_quality_eval(
        composer=[p],
        output_dir=tmp_path / "out",
        min_semantic_records=1,
        min_semantic_passes=1,
        max_semantic_failures=0,
        require_quality_pass=True,
    )
    assert manifest["quality_status"] == "PASS"


def test_troubleshooting_semantic_pass(tmp_path):
    p = _composer(
        tmp_path / "c" / "trace_net_engineering_intent_answer_composer_v1.json",
        "Why was nomenclature missing from the visual route evidence?",
        "troubleshooting_nomenclature",
        "Nomenclature was missing because the visual link stage did not carry a clean nomenclature field as proof [V6]. "
        "The OCR route recovered the nomenclature from raw OCR, and the merged visual evidence pack now carries it [O1].",
    )
    manifest = build_semantic_answer_quality_eval(
        composer=[p],
        output_dir=tmp_path / "out",
        min_semantic_records=1,
        min_semantic_passes=1,
        max_semantic_failures=0,
        require_quality_pass=True,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["records"][0]["semantic_quality_status"] == "PASS"


def test_semantic_failure_detects_bad_interchangeability_answer(tmp_path):
    p = _composer(
        tmp_path / "c" / "trace_net_engineering_intent_answer_composer_v1.json",
        "Is 120-50645-005 interchangeable with 120-50645-011?",
        "unsupported_interchangeability",
        "120-50645-005 and 120-50645-011 are interchangeable because they have the same name [V6] [V7].",
    )
    manifest = build_semantic_answer_quality_eval(
        composer=[p],
        output_dir=tmp_path / "out",
        min_semantic_records=1,
        min_semantic_passes=0,
        max_semantic_failures=1,
    )
    assert manifest["quality_status"] == "FAIL"
    assert manifest["summary"]["semantic_fail_count"] == 1
    assert manifest["records"][0]["missing_requirements"]


def test_check_semantic_answer_quality_eval(tmp_path):
    p = _composer(
        tmp_path / "c" / "trace_net_engineering_intent_answer_composer_v1.json",
        "Compare figure 69 and figure 75.",
        "comparison",
        "Comparison: Figure 69 uses 120-50645-005 [V6] [O1]. Figure 75 uses 120-50645-011 [V7] [O2]. "
        "This comparison does not prove interchangeability.",
    )
    manifest = build_semantic_answer_quality_eval(
        composer=[p],
        output_dir=tmp_path / "out",
        min_semantic_records=1,
        min_semantic_passes=1,
        max_semantic_failures=0,
        require_quality_pass=True,
    )
    result = check_semantic_answer_quality_eval(
        eval_set=tmp_path / "out" / "trace_net_engineering_semantic_answer_quality_eval_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        min_semantic_records=1,
        min_semantic_passes=1,
        max_semantic_failures=0,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "check.json").exists()
