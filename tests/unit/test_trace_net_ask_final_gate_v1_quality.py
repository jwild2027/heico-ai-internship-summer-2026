from __future__ import annotations

from pathlib import Path

from tiff.trace_net_ask_final_gate_v1 import check_ask_final_gate_quality, run_ask_final_gate
from test_trace_net_ask_final_gate_v1 import final_gate_payload, write_json


def test_quality_check_writes_json(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    write_json(path, final_gate_payload())
    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )
    quality = check_ask_final_gate_quality(
        report_path=Path(report["report_path"]),
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
        write_json_quality=True,
    )
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()


def test_quality_check_fails_embedding_dim(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    payload = final_gate_payload()
    payload["summary"]["embedding_dim"] = 384
    write_json(path, payload)
    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["embedding_dim"] == 384


def test_quality_check_fails_missing_ocr_note(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    payload = final_gate_payload(final_answer_text="Page 1 has cited evidence. [cite:one]")
    payload["summary"]["ocr_uncertainty_note_present"] = False
    write_json(path, payload)
    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["ocr_uncertainty_note_present"] is False
