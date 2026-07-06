from pathlib import Path
import runpy


def test_patch_script_exists():
    p = Path("scripts/apply_trace_net_h27e_retry_overlay_citation_patch_v1.py")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "_h27_append_individual_citation_instruction" in text
    assert "Do not group citations" in text
    assert "retry_prompt = _h27_apply_engram_answer_runner_overlay" in text
