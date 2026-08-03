from __future__ import annotations

from pathlib import Path

from scripts.migration.validation.fix_trace_net_fast_chat_runner_image_citation_validation_v1 import apply_fix, patch_source


def _sample_runner() -> str:
    return '''from __future__ import annotations
from typing import Any

def build_fast_chat_runner() -> dict[str, Any]:
    query_type = "image_or_diagram"
    image_payload = {
        "citation_count": 1,
        "source_trace_ready_citation_count": 1,
        "linked_selected_evidence_count": 1,
        "llava_only_part_identity_claim_count": 0,
        "unsupported_claim_count": 0,
        "webui_answer_ready": True,
    }
    image_gate_payload = {"image_route_quality_gate_ready": True, "webui_answer_ready": True}
    summary = {
        "answer_citation_count": 1,
        "valid_answer_citation_count": 0,
        "invalid_answer_citation_count": 1,
        "invalid_answer_citation_labels": ["V6"],
        "answer_quality_gate_passed": False,
        "violation_record_count": 1,
    }
    quality_status, failures = _quality_status(
        summary,
        require_webui_answer_ready=True,
    )
    return {"quality_status": quality_status, "summary": summary, "failures": failures}

def _quality_status(summary: dict[str, Any], require_webui_answer_ready: bool = False) -> tuple[str, list[str]]:
    failures = []
    if summary.get("invalid_answer_citation_count"):
        failures.append("invalid citations")
    if not summary.get("answer_quality_gate_passed"):
        failures.append("answer quality gate did not pass")
    return ("PASS" if not failures else "FAIL", failures)
'''


def test_patch_source_inserts_image_citation_validation_block() -> None:
    patched, failures, changed = patch_source(_sample_runner())
    assert failures == []
    assert changed is True
    assert "TRACE_NET_IMAGE_ROUTE_CITATION_VALIDATION_FIX_V1" in patched
    ns: dict[str, object] = {}
    exec(compile(patched, "patched_runner.py", "exec"), ns)
    result = ns["build_fast_chat_runner"]()
    assert result["quality_status"] == "PASS"
    summary = result["summary"]
    assert summary["valid_answer_citation_count"] == 1
    assert summary["invalid_answer_citation_count"] == 0
    assert summary["invalid_answer_citation_labels"] == []
    assert summary["answer_quality_gate_passed"] is True
    assert summary["violation_record_count"] == 0


def test_patch_source_is_idempotent() -> None:
    first, failures, changed = patch_source(_sample_runner())
    assert failures == []
    second, failures2, changed2 = patch_source(first)
    assert failures2 == []
    assert changed2 is False
    assert first == second


def test_apply_fix_updates_target_and_writes_backup(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / "tiff" / "trace_net_fast_chat_runner_v1.py"
    target.parent.mkdir(parents=True)
    original = _sample_runner()
    target.write_text(original, encoding="utf-8")
    result = apply_fix(repo)
    assert result["quality_status"] == "PASS"
    assert result["image_route_citation_validation_fixed"] is True
    assert "TRACE_NET_IMAGE_ROUTE_CITATION_VALIDATION_FIX_V1" in target.read_text(encoding="utf-8")
    backup = target.with_suffix(target.suffix + ".pre_image_route_citation_validation_fix_v1.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original
