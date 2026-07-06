import json
from pathlib import Path

from tiff.trace_net_engineering_engram_self_rag_critic_v1 import (
    build_self_rag_critic_manifest,
    check_self_rag_critic_manifest,
    critique_answer_record,
)


def test_good_record_passes():
    rec = {
        "question_id": "q18",
        "category": "pipeline_recovery",
        "grade": "GOOD",
        "proof_context_count": 3,
        "answer_citation_count": 2,
        "valid_answer_citation_count": 2,
        "source_trace_ready_citation_count": 2,
        "answer_text": "Answer: OK [V6] [O1]\nEvidence: cited.\nEngineering confidence: High\nLimits: no approval claim.",
    }
    out = critique_answer_record(rec)
    assert out["critic_status"] == "PASS"
    assert out["unsafe"] is False


def test_unknown_part_partial_is_expected_boundary():
    rec = {
        "question_id": "q25",
        "category": "unknown_part",
        "grade": "PARTIAL",
        "proof_context_count": 0,
        "answer_text": "Answer: Not found / not source-trace-ready. Evidence: No proof_context records were available. Engineering confidence: LOW. Limits: no proof.",
    }
    out = critique_answer_record(rec)
    assert out["critic_status"] == "EXPECTED_BOUNDARY"
    assert out["expected_unknown_boundary_partial"] is True


def test_missing_citations_with_proof_context_needs_repair():
    rec = {
        "question_id": "q18",
        "category": "pipeline_recovery",
        "grade": "PARTIAL",
        "proof_context_count": 5,
        "answer_citation_count": 0,
        "valid_answer_citation_count": 0,
        "source_trace_ready_citation_count": 0,
        "answer_text": "Answer: It changed the pipeline. Evidence: none. Engineering confidence: High. Limits: none.",
    }
    out = critique_answer_record(rec)
    assert out["critic_status"] == "REPAIR_RECOMMENDED"
    assert "proof_context_available_but_no_counted_citations" in out["findings"]


def _source_manifest(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "records": [
            {
                "question_id": "q12",
                "category": "interchangeability",
                "grade": "GOOD",
                "proof_context_count": 2,
                "answer_citation_count": 1,
                "valid_answer_citation_count": 1,
                "source_trace_ready_citation_count": 1,
                "answer_text": "Answer: Not proven [V6]\nEvidence: cited.\nEngineering confidence: High\nLimits: no interchangeability approval.",
            },
            {
                "question_id": "q25",
                "category": "unknown_part",
                "grade": "PARTIAL",
                "proof_context_count": 0,
                "answer_text": "Answer: Not found / not source-trace-ready. Evidence: no proof_context. Engineering confidence: LOW. Limits: not proven.",
            },
        ],
    }
    p = tmp_path / "answer.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_build_and_check_manifest(tmp_path):
    source = _source_manifest(tmp_path)
    result = build_self_rag_critic_manifest(
        answer_smoke=source,
        output_dir=tmp_path / "out",
        min_records=2,
        min_critic_pass_or_expected=2,
        max_repair_recommended=0,
        require_source_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["expected_boundary_count"] == 1
    check = check_self_rag_critic_manifest(
        critic=tmp_path / "out" / "trace_net_engineering_engram_self_rag_critic_v1.json",
        min_records=2,
        min_critic_pass_or_expected=2,
        require_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert check["quality_status"] == "PASS"
