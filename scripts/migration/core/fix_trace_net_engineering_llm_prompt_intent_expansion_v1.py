"""Patch TRACE-Net H13 LLM prompt with intent-specific engineering rules.

This fixer is intentionally narrow. It only edits
`tiff/trace_net_engineering_llm_answer_smoke_v1.py` to add category/question
specific prompt instructions for conservative-but-useful LLM answers.
"""
from __future__ import annotations

import argparse
import json
import py_compile
from pathlib import Path
from typing import Any, Dict, List

MODULE = "trace_net_engineering_llm_prompt_intent_expansion_fix_v1"
TARGET = Path("tiff/trace_net_engineering_llm_answer_smoke_v1.py")
REPORT_REL = Path("local_data/organization/trace_net/engineering_llm_prompt_intent_expansion_fix_v1/trace_net_engineering_llm_prompt_intent_expansion_fix_v1.json")

HELPER = r'''

def _intent_prompt_instructions(category: str, question: str) -> List[str]:
    """Return intent-specific LLM instructions for safer, more useful answers."""
    q = (question or "").lower()
    c = (category or "").lower()
    rules: List[str] = []

    if c in {"interchangeability", "replacement_limit"} or "interchange" in q or "replacement" in q:
        rules.append("Lead with not proven/cannot prove when asking about interchangeability or replacement approval unless proof_context explicitly states approval.")
        rules.append("If same or similar nomenclature appears for two part numbers, say that is identity evidence only, not interchangeability or replacement authority.")

    if c in {"installation_safety", "fit_limit", "effectivity_limit"} or "safe" in q or "install" in q or "fit" in q or "effectivity" in q:
        rules.append("For installation safety, fit approval, or effectivity questions, lead with no/not proven unless proof_context explicitly contains that approval.")
        rules.append("Then state what TRACE-Net can prove: part identity, figure link, nomenclature, and source pages when those citations are present.")

    if c in {"limitations", "summary_limit"} or "not prove" in q or "limitations" in q or "summaries alone" in q:
        rules.append("For limitation questions, answer in two parts: what TRACE-Net can prove from citations, then what it cannot prove from current evidence.")
        rules.append("For v2 summary questions, explicitly say summaries may guide planning/framing but cannot prove source claims; proof must come from proof_context citations.")

    if c in {"unknown_part", "unknown_figure"} or "999" in q:
        rules.append("If no proof_context records exist for an unknown part or figure, lead with not found / not source-trace-ready, not generic low-confidence language.")
        rules.append("Do not cite unrelated evidence for unknown part or figure questions.")

    if c in {"troubleshooting", "pipeline_recovery"} or "why" in q or "what changed" in q or "visual route need ocr" in q:
        rules.append("For TRACE-Net pipeline/debug questions, explain the pipeline behavior shown by context types: visual_figure_link establishes figure/part identity; ocr_nomenclature supplies OCR-backed name text.")
        rules.append("If visual and OCR proof_context records both exist for the same figure/part, do not answer only 'not proven'; explain what each route contributes and what remains limited.")
        rules.append("For raw OCR extractor questions, say the OCR route adds source-trace-ready nomenclature evidence when OCR records are present; avoid claiming more history than the context supports.")

    if c in {"evidence_support", "source_page", "evidence_explanation", "route_explanation"} or "evidence supports" in q or "source page" in q or "routes" in q or "visual proof" in q:
        rules.append("For evidence-support and route-explanation questions, explain why each cited evidence type matters, not just what it says.")
        rules.append("Mention visual proof separately from OCR/table proof when both are present.")

    if c in {"comparison", "nomenclature_summary"} or "compare" in q or "which figures" in q or "summarize the evidence" in q:
        rules.append("For comparisons or nomenclature summaries, cover all requested entities before limits; do not collapse the answer to only the first matching figure/part.")

    return rules
'''


def _insert_helper(text: str) -> str:
    if "def _intent_prompt_instructions" in text:
        return text
    marker = "def build_llm_prompt(\n"
    if marker not in text:
        raise ValueError("Could not find build_llm_prompt marker for helper insertion")
    return text.replace(marker, HELPER + "\n" + marker, 1)


def patch_text(text: str) -> str:
    original = text
    text = _insert_helper(text)

    old_sig = """def build_llm_prompt(
    *,
    question: str,
    runner_manifest: Mapping[str, Any],
    context_pack: Mapping[str, Any],
    max_guidance_items: int = 8,
) -> str:"""
    new_sig = """def build_llm_prompt(
    *,
    question: str,
    runner_manifest: Mapping[str, Any],
    context_pack: Mapping[str, Any],
    max_guidance_items: int = 8,
    category: str = "",
) -> str:"""
    if old_sig in text:
        text = text.replace(old_sig, new_sig, 1)
    elif new_sig not in text:
        raise ValueError("Could not find build_llm_prompt signature")

    old_lines = """    lines.append(f"QUESTION: {question}")
    lines.append(f"TASK_TYPE: {task_type}")"""
    new_lines = """    lines.append(f"QUESTION: {question}")
    if category:
        lines.append(f"QUESTION_CATEGORY: {category}")
    for rule in _intent_prompt_instructions(category, question):
        lines.append("INTENT_RULE: " + rule)
    lines.append(f"TASK_TYPE: {task_type}")"""
    if old_lines in text:
        text = text.replace(old_lines, new_lines, 1)
    elif new_lines not in text:
        raise ValueError("Could not find prompt question/task lines")

    old_call = "build_llm_prompt(question=question, runner_manifest=runner_manifest, context_pack=context_pack)"
    new_call = "build_llm_prompt(question=question, runner_manifest=runner_manifest, context_pack=context_pack, category=category)"
    if old_call in text:
        text = text.replace(old_call, new_call, 1)
    elif new_call not in text:
        raise ValueError("Could not find build_llm_prompt call site")

    if text == original:
        return text
    return text


def validate_text(text: str) -> List[str]:
    failures: List[str] = []
    required = [
        "def _intent_prompt_instructions",
        "category: str = \"\"",
        "QUESTION_CATEGORY",
        "INTENT_RULE:",
        "category=category",
        "visual_figure_link establishes figure/part identity",
        "not found / not source-trace-ready",
    ]
    for needle in required:
        if needle not in text:
            failures.append(f"missing required text: {needle}")
    return failures


def apply_patch(repo_root: Any) -> Dict[str, Any]:
    root = Path(repo_root)
    target = root / TARGET
    if not target.exists():
        return {
            "status": "TRACE_NET_ENGINEERING_LLM_PROMPT_INTENT_EXPANSION_FIX_APPLIED",
            "quality_status": "FAIL",
            "target": str(target),
            "changed": False,
            "failure_count": 1,
            "failures": [f"missing target: {target}"],
        }

    before = target.read_text(encoding="utf-8")
    after = patch_text(before)
    failures = validate_text(after)
    changed = after != before
    if not failures and changed:
        target.write_text(after, encoding="utf-8")
    if not failures:
        try:
            py_compile.compile(str(target), doraise=True)
        except Exception as exc:
            failures.append(f"compile failed: {type(exc).__name__}: {exc}")

    report = {
        "status": "TRACE_NET_ENGINEERING_LLM_PROMPT_INTENT_EXPANSION_FIX_APPLIED",
        "quality_status": "PASS" if not failures else "FAIL",
        "target": str(target),
        "changed": changed,
        "failure_count": len(failures),
        "failures": failures,
        "module": MODULE,
        "safety_contract": {
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
    }
    return report


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Patch H13 LLM answer smoke prompt with intent-specific engineering rules")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--require-quality-pass", action="store_true")
    args = parser.parse_args(argv)

    result = apply_patch(args.repo_root)
    report_path = Path(args.repo_root) / REPORT_REL
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("target=" + str(result.get("target")))
    print("changed=" + str(result.get("changed")))
    print("failure_count=" + str(result.get("failure_count")))
    print("report=" + str(report_path))
    if args.require_quality_pass and result.get("quality_status") != "PASS":
        raise SystemExit("quality_status is not PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
