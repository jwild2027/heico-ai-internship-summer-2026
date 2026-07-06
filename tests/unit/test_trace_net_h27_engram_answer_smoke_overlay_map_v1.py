from tiff.trace_net_h27_engram_answer_smoke_overlay_map_v1 import prepend_overlay_to_prompt, get_runtime_question_id


def test_prepend_overlay_boundary():
    out = prepend_overlay_to_prompt("BASE", "overlay guidance", "q12")
    assert "behavior guidance only" in out
    assert "Manual/source claims still require current proof_context citations." in out
    assert "BASE TRACE-NET ANSWER PROMPT" in out
    assert "q12" in out


def test_runtime_question_id_from_dict():
    assert get_runtime_question_id({"question": {"question_id": "q18"}}) == "q18"
