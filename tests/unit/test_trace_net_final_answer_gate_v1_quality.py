from __future__ import annotations

import json
from pathlib import Path

from tiff import trace_net_final_answer_gate_v1 as mod
from tests.unit.test_trace_net_final_answer_gate_v1 import cleaner_payload, clean_claim, write_json


def test_quality_check_passes_for_written_report(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.json"
    out_dir = tmp_path / "out"
    write_json(clean_path, cleaner_payload())
    report = mod.run_final_answer_gate(
        clean_snippets_path=clean_path,
        output_dir=out_dir,
        min_final_claims=1,
        require_clean_snippet_quality_pass=True,
        require_clean_snippet_answer_status="CLEAN_SNIPPETS_ONLY",
        require_embedding_dim=1024,
        require_final_answer_allowed=True,
    )

    quality = mod.check_final_answer_gate_quality(
        report_path=Path(report["report_path"]),
        min_final_claims=1,
        require_clean_snippet_quality_pass=True,
        require_clean_snippet_answer_status="CLEAN_SNIPPETS_ONLY",
        require_embedding_dim=1024,
        require_final_answer_allowed=True,
        write_json_quality=True,
    )

    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()


def test_quality_check_fails_without_final_answer_allowed(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.json"
    out_dir = tmp_path / "out"
    write_json(clean_path, cleaner_payload([clean_claim(citation="")]))
    report = mod.run_final_answer_gate(clean_snippets_path=clean_path, output_dir=out_dir, min_final_claims=1)

    quality = mod.check_final_answer_gate_quality(
        report_path=Path(report["report_path"]),
        min_final_claims=1,
        require_final_answer_allowed=True,
    )

    assert quality["status"] == "FAIL"
    failed = [check["name"] for check in quality["checks"] if not check["passed"]]
    assert "min_final_claims" in failed
    assert "final_answer_allowed" in failed


def test_quality_check_fails_when_answer_loses_ocr_note(tmp_path: Path) -> None:
    payload = cleaner_payload()
    report = mod.build_final_answer_gate_report(clean_snippet_payload=payload)
    report["final_answer_text"] = "Final answer without uncertainty note [cite:source_text:p000001:abc]."
    report["summary"] = mod.summarize_final_answer_gate(
        clean_snippet_payload=payload,
        final_claims=report["final_claims"],
        blocked_claims=report["blocked_final_claims"],
        final_answer_text=report["final_answer_text"],
        composer_info={"composer_mode": "template"},
    )
    path = tmp_path / "bad.json"
    write_json(path, report)

    quality = mod.check_final_answer_gate_quality(report_path=path, min_final_claims=1, require_final_answer_allowed=True)

    assert quality["status"] == "FAIL"
    failed = [check["name"] for check in quality["checks"] if not check["passed"]]
    assert "ocr_uncertainty_note_present" in failed
