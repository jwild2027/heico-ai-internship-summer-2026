from scripts.fix_trace_net_fast_chat_runner_image_route_precedence_v1 import patch_source_text


def _source() -> str:
    return '''
def build_fast_chat_runner(*, question, part_number=None, part_family=None, figure=None, item=None, image_visual_evidence_pack=None):
    query_plan = detect_query_type(question, part_number=part_number, part_family=part_family, figure=figure, item=item)
    query_type = query_plan["query_type"]
    if query_type == "exact_part_number":
        pass
    elif query_type == "image_or_diagram":
        pass
    elif query_type == "figure_or_item":
        pass
'''


def test_patches_query_plan_assignment_and_keeps_python_valid():
    patched, failures, changed = patch_source_text(_source())
    assert failures == []
    assert changed is True
    assert "TRACE_NET_IMAGE_ROUTE_PRECEDENCE_FIX_V1" in patched
    assert 'query_plan["query_type"] = "image_or_diagram"' in patched
    assert 'query_plan["query_route"] = "fast_image_diagram_answer"' in patched


def test_is_idempotent():
    patched, failures, changed = patch_source_text(_source())
    assert failures == []
    patched2, failures2, changed2 = patch_source_text(patched)
    assert failures2 == []
    assert changed2 is False
    assert patched2 == patched


def test_requires_image_route_branch():
    src = _source().replace('    elif query_type == "image_or_diagram":\n        pass\n', '')
    _patched, failures, changed = patch_source_text(src)
    assert changed is False
    assert any("image_or_diagram route branch" in f for f in failures)
