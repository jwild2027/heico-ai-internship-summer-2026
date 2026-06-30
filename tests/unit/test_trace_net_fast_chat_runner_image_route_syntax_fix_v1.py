from pathlib import Path
import ast

from scripts.fix_trace_net_fast_chat_runner_image_route_syntax_v1 import _repair_text


def test_repair_malformed_inline_if() -> None:
    bad = '    if require_part_family_query and summary.get("query_type") != "part_family": failures.append("query_type is not part_family") if require_image_diagram_query and summary.get("query_type") != "image_or_diagram": failures.append("query_type is not image_or_diagram")\n'
    fixed, changed, reason = _repair_text(bad)
    assert changed is True
    assert reason == "fixed_malformed_inline_if"
    assert 'if require_part_family_query and summary.get("query_type") != "part_family":' in fixed
    assert 'if require_image_diagram_query and summary.get("query_type") != "image_or_diagram":' in fixed
    ast.parse("def f():\n" + fixed)


def test_repair_is_idempotent_for_fixed_anchor() -> None:
    text = '''    if require_part_family_query and summary.get("query_type") != "part_family":\n        failures.append("query_type is not part_family")\n    if require_image_diagram_query and summary.get("query_type") != "image_or_diagram":\n        failures.append("query_type is not image_or_diagram")\n'''
    fixed, changed, reason = _repair_text(text)
    assert fixed == text
    assert changed is False
    assert reason == "already_fixed_or_anchor_present"
