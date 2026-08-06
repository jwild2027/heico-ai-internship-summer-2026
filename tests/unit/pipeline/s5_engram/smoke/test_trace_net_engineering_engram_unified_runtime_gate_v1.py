
import json
from pathlib import Path

from tiff.trace_net_engineering_engram_unified_runtime_gate_v1 import (
    build_unified_runtime_gate,
    check_unified_runtime_gate,
)


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path):
    qids = ["q12", "q16", "q18", "q25", "q29"]
    answer = {
        "quality_status": "PASS",
        "summary": {"answer_permission_count": 0, "write_attempt_count": 0, "unsafe_finding_count": 0},
        "records": [
            {"question_id": q, "question": f"Question {q}", "grade": "PARTIAL" if q == "q25" else "GOOD", "answer_text": "Answer [A1]"}
            for q in qids
        ],
    }
    critic = {
        "quality_status": "PASS",
        "summary": {"answer_permission_count": 0, "write_attempt_count": 0, "unsafe_finding_count": 0},
        "critic_records": [
            {
                "question_id": q,
                "source_grade": "PARTIAL" if q == "q25" else "GOOD",
                "critic_status": "EXPECTED_BOUNDARY" if q == "q25" else "PASS",
                "expected_unknown_boundary_partial": q == "q25",
                "repair_recommended": False,
            }
            for q in qids
        ],
    }
    crag = {
        "quality_status": "PASS",
        "summary": {"answer_permission_count": 0, "write_attempt_count": 0, "unsafe_finding_count": 0},
        "crag_repair_records": [
            {"question_id": q, "crag_status": "NO_REPAIR_NEEDED", "repair_attempted": False}
            for q in qids
        ],
    }
    qdrant = {
        "quality_status": "PASS",
        "summary": {"answer_permission_count": 0, "write_attempt_count": 0, "unsafe_finding_count": 0},
        "local_retrieval_records": [
            {"query_id": "q_interchangeability", "results": [{"memory_layer": "procedural_memory", "atom_id": "a", "score": 0.5}]},
            {"query_id": "q_visual_ocr", "results": [{"memory_layer": "semantic_memory", "atom_id": "b", "score": 0.5}]},
            {"query_id": "q_safe_generic", "results": [{"memory_layer": "critic_memory", "atom_id": "c", "score": 0.5}]},
            {"query_id": "q_unknown_part", "results": [{"memory_layer": "working_memory", "atom_id": "d", "score": 0.5}]},
            {"query_id": "q_summary_limit", "results": [{"memory_layer": "working_memory", "atom_id": "e", "score": 0.5}]},
        ],
    }
    feedback_records = [
        {"feedback_id": f"fb_{q}", "source_question_id": q, "rating": "expected_boundary" if q == "q25" else "thumbs_up"}
        for q in qids
    ]
    candidates = [
        {"candidate_id": f"cand_{q}", "feedback_id": f"fb_{q}", "memory_layer": "episodic_memory", "proof_role": "guidance_only"}
        for q in qids
    ]
    feedback = {
        "quality_status": "PASS",
        "summary": {"answer_permission_count": 0, "write_attempt_count": 0, "unsafe_finding_count": 0},
        "feedback_records": feedback_records,
        "candidate_records": candidates,
    }
    paths = {}
    for name, data in (("answer", answer), ("critic", critic), ("crag", crag), ("qdrant", qdrant), ("feedback", feedback)):
        paths[name] = _write(tmp_path / f"{name}.json", data)
    return paths


def test_build_unified_runtime_gate_passes(tmp_path):
    p = _fixtures(tmp_path)
    result = build_unified_runtime_gate(
        answer_smoke=p["answer"],
        critic=p["critic"],
        crag_repair=p["crag"],
        qdrant_adapter=p["qdrant"],
        feedback_ledger=p["feedback"],
        output_dir=tmp_path / "out",
        require_answer_quality_pass=True,
        require_critic_quality_pass=True,
        require_crag_quality_pass=True,
        require_qdrant_quality_pass=True,
        require_feedback_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["self_rag_connected"] is True
    assert result["summary"]["crag_connected"] is True
    assert result["summary"]["qdrant_vector_adapter_connected"] is True
    assert result["summary"]["postgres_feedback_ledger_connected"] is True
    assert result["summary"]["expected_boundary_count"] == 1


def test_check_unified_runtime_gate_passes(tmp_path):
    p = _fixtures(tmp_path)
    result = build_unified_runtime_gate(
        answer_smoke=p["answer"], critic=p["critic"], crag_repair=p["crag"],
        qdrant_adapter=p["qdrant"], feedback_ledger=p["feedback"], output_dir=tmp_path / "out",
    )
    check = check_unified_runtime_gate(
        tmp_path / "out" / "trace_net_engineering_engram_unified_runtime_gate_v1.json",
        require_quality_pass=True,
        require_connections=True,
        require_no_answer_permission=True,
    )
    assert check["quality_status"] == "PASS"


def test_answer_permission_fails_when_required(tmp_path):
    p = _fixtures(tmp_path)
    data = json.loads(p["answer"].read_text())
    data["summary"]["answer_permission_count"] = 1
    p["answer"].write_text(json.dumps(data), encoding="utf-8")
    result = build_unified_runtime_gate(
        answer_smoke=p["answer"], critic=p["critic"], crag_repair=p["crag"],
        qdrant_adapter=p["qdrant"], feedback_ledger=p["feedback"], output_dir=tmp_path / "out",
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"
    assert "answer_permission" in " ".join(result["summary"]["quality_failures"])


def test_runtime_records_include_proof_boundary(tmp_path):
    p = _fixtures(tmp_path)
    result = build_unified_runtime_gate(
        answer_smoke=p["answer"], critic=p["critic"], crag_repair=p["crag"],
        qdrant_adapter=p["qdrant"], feedback_ledger=p["feedback"], output_dir=tmp_path / "out",
    )
    for rec in result["runtime_records"]:
        assert "proof_context citations" in rec["proof_boundary"]
        assert rec["answer_permission"] is False
        assert rec["source_truth_mutation_allowed"] is False
