from scripts.migration.core.fix_trace_net_engineering_llm_prompt_intent_expansion_v1 import patch_text, validate_text


def _sample() -> str:
    return '''
from typing import Any, Dict, List, Mapping

def _format_proof_item(item: Mapping[str, Any]) -> str:
    return "x"

def build_llm_prompt(
    *,
    question: str,
    runner_manifest: Mapping[str, Any],
    context_pack: Mapping[str, Any],
    max_guidance_items: int = 8,
) -> str:
    lines: List[str] = []
    task_type = "x"
    lines.append(f"QUESTION: {question}")
    lines.append(f"TASK_TYPE: {task_type}")
    return "\\n".join(lines)


def build_engineering_llm_answer_smoke():
    question = "Why was nomenclature missing from the visual route evidence?"
    runner_manifest = {}
    context_pack = {}
    category = "troubleshooting"
    prompt = build_llm_prompt(question=question, runner_manifest=runner_manifest, context_pack=context_pack)
    return prompt
'''


def test_patch_inserts_intent_helper_and_category_signature():
    fixed = patch_text(_sample())
    assert "def _intent_prompt_instructions" in fixed
    assert 'category: str = ""' in fixed
    assert "QUESTION_CATEGORY" in fixed
    assert "INTENT_RULE" in fixed


def test_patch_updates_prompt_call_site():
    fixed = patch_text(_sample())
    assert "category=category" in fixed


def test_patch_is_idempotent():
    fixed = patch_text(_sample())
    fixed2 = patch_text(fixed)
    assert fixed2 == fixed


def test_validate_text_passes_after_patch():
    fixed = patch_text(_sample())
    assert validate_text(fixed) == []
