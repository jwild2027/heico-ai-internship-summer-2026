import json
from pathlib import Path

from tiff.trace_net_engineering_answer_runner_overlay_context_pack_v1 import (
    build_overlay_context_pack_manifest,
    build_work_order_context_pack,
    check_overlay_context_pack_manifest,
)


def test_work_order_context_pack_keeps_overlay_guidance_only():
    pack = build_work_order_context_pack(
        question_id="q1",
        question="Is PN A eligible?",
        overlay_text="Engram says require explicit proof_context citations.",
        proof_context_count=0,
    )
    text = pack["prompt_text"]
    assert pack["answer_permission"] is False
    assert pack["source_truth_mutation_allowed"] is False
    assert pack["engram_is_proof"] is False
    assert "behavior guidance only" in text
    assert "proof_context" in text
    assert "not source-trace-ready" in text


def test_overlay_context_pack_manifest_builds_from_smoke_and_map(tmp_path: Path):
    prompt = tmp_path / "q1_prompt.txt"
    prompt.write_text("SOURCE PROMPT\nCurrent proof_context:\nNone supplied.", encoding="utf-8")
    smoke = tmp_path / "source_answer_smoke.json"
    smoke.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [{
            "question_id": "q1",
            "question": "Is PN A eligible?",
            "grade": "PARTIAL",
            "proof_context_count": 0,
            "prompt_path": str(prompt),
            "answer_permission": False,
        }],
        "summary": {"answer_permission_count": 0, "write_attempt_count": 0},
    }), encoding="utf-8")
    overlay = tmp_path / "overlay_map.json"
    overlay.write_text(json.dumps({
        "q1": {"overlay_text": "TRACE-NET overlay. Engram guidance only; proof_context required."}
    }), encoding="utf-8")
    manifest = build_overlay_context_pack_manifest(
        source_answer_smoke=smoke,
        overlay_map=overlay,
        output_dir=tmp_path / "out",
        question_ids="q1",
        min_records=1,
        require_source_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["matched_overlay_count"] == 1
    checked = check_overlay_context_pack_manifest(
        context_pack=tmp_path / "out" / "trace_net_engineering_answer_runner_overlay_context_pack_v1.json",
        min_records=1,
        min_matched_overlays=1,
        require_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert checked["quality_status"] == "PASS"
