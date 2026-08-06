from __future__ import annotations

from datetime import datetime
from pathlib import Path
import py_compile
import shutil

TARGET = Path("tiff/trace_net_engineering_llm_answer_smoke_v1.py")

HELPER = r'''

def _h27_append_individual_citation_instruction(prompt: str) -> str:
    """Append a narrow citation-syntax guard for Engram overlay/retry prompts.

    This is behavior-only prompt guidance. It does not add proof, grant answer
    permission, or alter source-truth artifacts. It only tells the LLM to cite
    existing proof-context labels as individual bracketed labels so the smoke
    citation counter can validate them.
    """
    text = prompt or ""
    required = (
        "Citation syntax requirement: When citing proof_context labels, cite each label "
        "individually, for example [V6] [V7] [O1]. Do not group citations inside one "
        "bracket like [V6, V7, O1]. Engram guidance is not proof."
    )
    if required in text:
        return text
    return text.rstrip() + "\n\n" + required + "\n"
'''


def _insert_after_function(src: str) -> tuple[str, bool]:
    if "def _h27_append_individual_citation_instruction" in src:
        return src, False
    marker = "def build_engineering_llm_answer_smoke("
    if marker not in src:
        raise RuntimeError("could not find build_engineering_llm_answer_smoke anchor")
    idx = src.index(marker)
    return src[:idx] + HELPER + "\n" + src[idx:], True


def _insert_after_first_apply(src: str) -> tuple[str, bool]:
    if "prompt = _h27_append_individual_citation_instruction(prompt)" in src:
        return src, False
    anchor = (
        "                    prompt = _h27_apply_engram_answer_runner_overlay(\n"
        "                        prompt,\n"
        "                        qrec,\n"
        "                        _h27_engram_answer_runner_overlay_map_records,\n"
        "                    )\n"
    )
    if anchor not in src:
        raise RuntimeError("could not find H27 full-prompt overlay apply anchor")
    replacement = anchor + "                    prompt = _h27_append_individual_citation_instruction(prompt)\n"
    return src.replace(anchor, replacement, 1), True


def _insert_retry_apply(src: str) -> tuple[str, bool]:
    if "retry_prompt = _h27_append_individual_citation_instruction(retry_prompt)" in src:
        return src, False
    anchor = "                        _write_text(retry_prompt_path, retry_prompt)\n"
    if anchor not in src:
        raise RuntimeError("could not find retry prompt write anchor")
    block = (
        "                        retry_prompt = _h27_apply_engram_answer_runner_overlay(\n"
        "                            retry_prompt,\n"
        "                            qrec,\n"
        "                            _h27_engram_answer_runner_overlay_map_records,\n"
        "                        )\n"
        "                        retry_prompt = _h27_append_individual_citation_instruction(retry_prompt)\n"
    )
    return src.replace(anchor, block + anchor, 1), True


def main() -> int:
    if not TARGET.exists():
        print("status=TRACE_NET_H27E_RETRY_OVERLAY_CITATION_PATCH_FAILED")
        print(f"error=target_missing:{TARGET}")
        return 1

    original = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(
        TARGET.suffix + ".bak_h27e_retry_overlay_citation_patch_v1_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup.write_text(original, encoding="utf-8")

    try:
        src = original
        # Refuse to patch unless H27 overlay infrastructure is present.
        required_markers = [
            "def _h27_load_engram_answer_runner_overlay_map",
            "def _h27_apply_engram_answer_runner_overlay",
            "_h27_engram_answer_runner_overlay_map_records",
            "engram_answer_runner_overlay_map: str | Path | None = None",
        ]
        missing = [m for m in required_markers if m not in src]
        if missing:
            raise RuntimeError("missing_h27_markers:" + ",".join(missing))

        src, helper_inserted = _insert_after_function(src)
        src, full_prompt_citation_guard_inserted = _insert_after_first_apply(src)
        src, retry_overlay_and_citation_guard_inserted = _insert_retry_apply(src)

        TARGET.write_text(src, encoding="utf-8")
        py_compile.compile(str(TARGET), doraise=True)

    except Exception as e:
        TARGET.write_text(original, encoding="utf-8")
        print("status=TRACE_NET_H27E_RETRY_OVERLAY_CITATION_PATCH_FAILED_RESTORED")
        print(f"error={type(e).__name__}: {e}")
        print(f"backup={backup}")
        return 1

    print("status=TRACE_NET_H27E_RETRY_OVERLAY_CITATION_PATCH_APPLIED")
    print("quality_status=PASS")
    print(f"target={TARGET}")
    print(f"helper_inserted={helper_inserted}")
    print(f"full_prompt_citation_guard_inserted={full_prompt_citation_guard_inserted}")
    print(f"retry_overlay_and_citation_guard_inserted={retry_overlay_and_citation_guard_inserted}")
    print(f"backup={backup}")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
