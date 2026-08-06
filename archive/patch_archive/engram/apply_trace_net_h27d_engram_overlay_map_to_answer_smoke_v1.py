from __future__ import annotations

from datetime import datetime
from pathlib import Path
import py_compile

TARGET = Path("tiff/trace_net_engineering_llm_answer_smoke_v1.py")

HELPER_BLOCK = r'''

# --- H27D Engram answer-runner overlay-map support (explicit opt-in) ---
def _h27_load_engram_answer_runner_overlay_map(path):
    """Load an H26/H27 overlay map artifact without performing live DB/vector IO."""
    if not path:
        return {}
    import json
    from pathlib import Path as _H27Path

    p = _H27Path(path)
    if not p.exists():
        raise FileNotFoundError(f"H27 overlay map not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))

    def _text_from_record(rec):
        if not isinstance(rec, dict):
            return ""
        for key in (
            "overlay_text",
            "guidance_overlay_text",
            "prompt_overlay_text",
            "integration_prompt_text",
            "prompt_guidance_text",
            "overlay_text_preview",
        ):
            value = rec.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    out = {}

    if isinstance(data, dict):
        # Direct map form: {"q12": "overlay text"} or {"q12": {record}}
        for key, value in data.items():
            if isinstance(key, str) and key.startswith("q"):
                if isinstance(value, str):
                    out[key] = value.strip()
                elif isinstance(value, dict):
                    text = _text_from_record(value)
                    if text:
                        out[key] = text

        # Manifest/list forms used by H24/H26-style artifacts.
        for list_key in (
            "overlay_map_records",
            "overlay_records",
            "gate_records",
            "records",
            "prompt_overlay_records",
        ):
            records = data.get(list_key)
            if isinstance(records, list):
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    qid = rec.get("question_id") or rec.get("target_question_id") or rec.get("answer_runner_question_id")
                    text = _text_from_record(rec)
                    if isinstance(qid, str) and qid and text:
                        out[qid] = text

        nested = data.get("overlay_map")
        if isinstance(nested, dict):
            for key, value in nested.items():
                if isinstance(value, str):
                    out[str(key)] = value.strip()
                elif isinstance(value, dict):
                    text = _text_from_record(value)
                    if text:
                        out[str(key)] = text

    elif isinstance(data, list):
        for rec in data:
            if not isinstance(rec, dict):
                continue
            qid = rec.get("question_id") or rec.get("target_question_id")
            text = _text_from_record(rec)
            if isinstance(qid, str) and qid and text:
                out[qid] = text

    return out


def _h27_question_id_from_record(qrec):
    if isinstance(qrec, dict):
        for key in ("question_id", "id", "qid"):
            value = qrec.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _h27_apply_engram_answer_runner_overlay(prompt, qrec, overlay_map_records):
    """Prepend retrieved Engram behavior guidance; never treats it as proof."""
    if not overlay_map_records:
        return prompt
    qid = _h27_question_id_from_record(qrec)
    overlay = overlay_map_records.get(qid)
    if not overlay:
        return prompt
    boundary = (
        "TRACE-NET H27 RETRIEVED ENGRAM OVERLAY — BEHAVIOR ONLY, NOT PROOF\n"
        "Manual/source claims still require current proof_context citations.\n"
        "Do not let Engram guidance grant answer permission, mutate source truth, "
        "or replace proof_context.\n"
    )
    return boundary + "\n" + overlay.strip() + "\n\n--- ORIGINAL ANSWER-RUNNER PROMPT ---\n" + (prompt or "")
# --- end H27D overlay-map support ---
'''


def _insert_param(src: str) -> tuple[str, bool]:
    if "engram_answer_runner_overlay_map" in src:
        return src, False
    marker = "def build_engineering_llm_answer_smoke("
    start = src.find(marker)
    if start < 0:
        raise RuntimeError("could not find build_engineering_llm_answer_smoke signature")
    # Find the first line after the def start that closes the signature.
    line_start = src.rfind("\n", 0, start) + 1
    colon = src.find(":\n", start)
    if colon < 0:
        raise RuntimeError("could not find end of build_engineering_llm_answer_smoke signature")
    sig = src[line_start:colon + 2]
    lines = sig.splitlines(keepends=True)
    insert_at = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith(")"):
            insert_at = i
            break
    if insert_at is None:
        raise RuntimeError("could not find closing signature line")
    lines.insert(insert_at, "    engram_answer_runner_overlay_map: str | Path | None = None,\n")
    new_sig = "".join(lines)
    return src[:line_start] + new_sig + src[colon + 2:], True


def _insert_parser_arg(src: str) -> tuple[str, bool]:
    if "--engram-answer-runner-overlay-map" in src:
        return src, False
    marker = "    return parser"
    idx = src.find(marker, src.find("def build_arg_parser"))
    if idx < 0:
        raise RuntimeError("could not find return parser anchor")
    arg = '    parser.add_argument("--engram-answer-runner-overlay-map", default=None)\n'
    return src[:idx] + arg + src[idx:], True


def _insert_helper_block(src: str) -> tuple[str, bool]:
    if "def _h27_load_engram_answer_runner_overlay_map" in src:
        return src, False
    marker = "def build_engineering_llm_answer_smoke("
    idx = src.find(marker)
    if idx < 0:
        raise RuntimeError("could not find insertion anchor for helper block")
    return src[:idx] + HELPER_BLOCK + "\n" + src[idx:], True


def _insert_map_load(src: str) -> tuple[str, bool]:
    if "_h27_engram_answer_runner_overlay_map_records = _h27_load_engram_answer_runner_overlay_map" in src:
        return src, False
    anchor = "    for idx, qrec in enumerate(questions, 1):"
    idx = src.find(anchor)
    if idx < 0:
        raise RuntimeError("could not find question loop anchor")
    insert = (
        "    _h27_engram_answer_runner_overlay_map_records = "
        "_h27_load_engram_answer_runner_overlay_map(engram_answer_runner_overlay_map)\n"
    )
    return src[:idx] + insert + src[idx:], True


def _insert_overlay_apply(src: str) -> tuple[str, bool]:
    if "_h27_apply_engram_answer_runner_overlay(prompt, qrec" in src:
        return src, False
    anchor = "                    _write_text(prompt_path, prompt)"
    idx = src.find(anchor)
    if idx < 0:
        raise RuntimeError("could not find exact prompt write anchor: _write_text(prompt_path, prompt)")
    insert = (
        "                    prompt = _h27_apply_engram_answer_runner_overlay(\n"
        "                        prompt, qrec, _h27_engram_answer_runner_overlay_map_records\n"
        "                    )\n"
    )
    return src[:idx] + insert + src[idx:], True


def main() -> int:
    if not TARGET.exists():
        print("status=TRACE_NET_H27D_ENGRAM_OVERLAY_MAP_PATCH_FAILED")
        print(f"error=missing target {TARGET}")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(TARGET.suffix + ".bak_h27d_engram_overlay_map_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup.write_text(src, encoding="utf-8")

    changed = {}
    try:
        src, changed["helper_block_inserted"] = _insert_helper_block(src)
        src, changed["function_param_inserted"] = _insert_param(src)
        src, changed["parser_arg_inserted"] = _insert_parser_arg(src)
        src, changed["overlay_map_load_inserted"] = _insert_map_load(src)
        src, changed["overlay_apply_inserted"] = _insert_overlay_apply(src)
    except Exception as exc:
        print("status=TRACE_NET_H27D_ENGRAM_OVERLAY_MAP_PATCH_FAILED")
        print(f"error={exc}")
        print(f"backup={backup}")
        return 1

    TARGET.write_text(src, encoding="utf-8")
    try:
        py_compile.compile(str(TARGET), doraise=True)
    except Exception as exc:
        TARGET.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        print("status=TRACE_NET_H27D_ENGRAM_OVERLAY_MAP_PATCH_FAILED")
        print("error=patched file failed py_compile; restored backup")
        print(f"compile_error={exc}")
        print(f"backup={backup}")
        return 1

    print("status=TRACE_NET_H27D_ENGRAM_OVERLAY_MAP_PATCH_APPLIED")
    print("quality_status=PASS")
    print(f"target={TARGET}")
    for k, v in changed.items():
        print(f"{k}={v}")
    print(f"backup={backup}")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
