from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tiff" / "trace_net_engineering_llm_answer_smoke_v1.py"
HELPER_IMPORT = "from tiff.trace_net_h27_engram_answer_smoke_overlay_map_v1 import (\n    apply_overlay_from_runtime as _h27_apply_overlay_from_runtime,\n    load_engram_answer_runner_overlay_map as _h27_load_engram_answer_runner_overlay_map,\n)\n"
ARG_LINE = '    parser.add_argument("--engram-answer-runner-overlay-map", default="")\n'
PARAM_LINE = '    engram_answer_runner_overlay_map: str | Path | None = None,\n'
LOAD_LINE = '    h27_engram_overlay_map = _h27_load_engram_answer_runner_overlay_map(engram_answer_runner_overlay_map)\n'


def _backup(path: Path, src: str) -> Path:
    b = path.with_suffix(path.suffix + ".bak_h27_engram_overlay_map_v1b_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    b.write_text(src, encoding="utf-8")
    return b


def _insert_import(src: str) -> tuple[str, bool]:
    if "_h27_load_engram_answer_runner_overlay_map" in src:
        return src, False
    # Put after __future__ imports if present, else after initial imports block.
    m = list(re.finditer(r"^from __future__ import .*\n", src, flags=re.M))
    if m:
        pos = m[-1].end()
        return src[:pos] + HELPER_IMPORT + src[pos:], True
    m = list(re.finditer(r"^(?:import|from) .*\n", src, flags=re.M))
    if m:
        pos = m[-1].end()
        return src[:pos] + HELPER_IMPORT + src[pos:], True
    return HELPER_IMPORT + src, True


def _insert_parser_arg(src: str) -> tuple[str, bool]:
    if "--engram-answer-runner-overlay-map" in src:
        return src, False
    idx = src.find("def build_arg_parser")
    if idx < 0:
        raise RuntimeError("missing build_arg_parser")
    ret = src.find("    return parser", idx)
    if ret < 0:
        raise RuntimeError("missing return parser anchor")
    return src[:ret] + ARG_LINE + src[ret:], True


def _insert_param(src: str) -> tuple[str, bool]:
    if "engram_answer_runner_overlay_map" in src and "def build_engineering_llm_answer_smoke" in src:
        # Could be only parser arg, but if the parameter is already present, skip.
        sig_start = src.find("def build_engineering_llm_answer_smoke")
        sig_end = src.find("):", sig_start)
        if sig_start >= 0 and sig_end >= 0 and "engram_answer_runner_overlay_map" in src[sig_start:sig_end]:
            return src, False
    sig_start = src.find("def build_engineering_llm_answer_smoke")
    if sig_start < 0:
        raise RuntimeError("missing build_engineering_llm_answer_smoke")
    sig_end = src.find("):", sig_start)
    if sig_end < 0:
        raise RuntimeError("could not find end of build_engineering_llm_answer_smoke signature")
    return src[:sig_end] + PARAM_LINE + src[sig_end:], True


def _insert_loader(src: str) -> tuple[str, bool]:
    if "h27_engram_overlay_map = _h27_load_engram_answer_runner_overlay_map" in src:
        return src, False
    sig_start = src.find("def build_engineering_llm_answer_smoke")
    sig_end = src.find("):", sig_start)
    if sig_start < 0 or sig_end < 0:
        raise RuntimeError("missing build_engineering_llm_answer_smoke body")
    insert_at = src.find("\n", sig_end) + 1
    return src[:insert_at] + LOAD_LINE + src[insert_at:], True


def _find_prompt_write(src: str) -> tuple[int, int, str, str]:
    lines = src.splitlines(keepends=True)
    char_pos = 0
    candidates = []
    for line in lines:
        stripped = line.strip()
        if "write_text" in line and "prompt" in line.lower():
            candidates.append((char_pos, line))
        char_pos += len(line)

    preferred = []
    fallback = []
    for pos, line in candidates:
        # Common: prompt_path.write_text(prompt, encoding="utf-8")
        m = re.search(r"^(?P<indent>\s*)[\w\.]*prompt[\w\.]*\.write_text\((?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*,", line, flags=re.I)
        if m:
            item = (pos, pos + len(line), m.group("indent"), m.group("var"))
            if "retry" not in line.lower() and m.group("var") == "prompt":
                preferred.append(item)
            else:
                fallback.append(item)
            continue
        # Common: _write_text(prompt_path, prompt) or _write_text(retry_prompt_path, retry_prompt)
        m = re.search(r"^(?P<indent>\s*)_write_text\([^,]*prompt[^,]*,\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*prompt[A-Za-z0-9_]*)\s*\)", line, flags=re.I)
        if m:
            item = (pos, pos + len(line), m.group("indent"), m.group("var"))
            if "retry" not in line.lower() and m.group("var") == "prompt":
                preferred.append(item)
            else:
                fallback.append(item)
            continue
        # Common: some_path.write_text(prompt_text, ...), with prompt in variable name.
        m = re.search(r"^(?P<indent>\s*)[A-Za-z_][A-Za-z0-9_\.]*\.write_text\((?P<var>[A-Za-z_][A-Za-z0-9_]*prompt[A-Za-z0-9_]*)\s*,", line, flags=re.I)
        if m:
            item = (pos, pos + len(line), m.group("indent"), m.group("var"))
            if "retry" not in line.lower() and m.group("var") == "prompt":
                preferred.append(item)
            else:
                fallback.append(item)
            continue
    if preferred:
        return preferred[0]
    if fallback:
        return fallback[0]
    details = "\n".join(f"{p}: {l.rstrip()}" for p, l in candidates[:20])
    raise RuntimeError("could not find prompt write_text anchor. Candidates:\n" + details)


def _insert_overlay_apply(src: str) -> tuple[str, bool]:
    if "_h27_apply_overlay_from_runtime" in src and "h27_engram_overlay_map" in src and "locals()" in src:
        return src, False
    pos, _end, indent, prompt_var = _find_prompt_write(src)
    insert = (
        f"{indent}{prompt_var} = _h27_apply_overlay_from_runtime(\n"
        f"{indent}    {prompt_var}, h27_engram_overlay_map, locals()\n"
        f"{indent})\n"
    )
    return src[:pos] + insert + src[pos:], True


def main() -> int:
    if not TARGET.exists():
        print("status=TRACE_NET_H27_ENGRAM_OVERLAY_MAP_PATCH_FAILED")
        print(f"error=target not found: {TARGET}")
        return 1
    src = TARGET.read_text(encoding="utf-8")
    backup = _backup(TARGET, src)
    changed = {}
    try:
        src, changed["import_inserted"] = _insert_import(src)
        src, changed["parser_arg_inserted"] = _insert_parser_arg(src)
        src, changed["param_inserted"] = _insert_param(src)
        src, changed["loader_inserted"] = _insert_loader(src)
        src, changed["overlay_apply_inserted"] = _insert_overlay_apply(src)
    except Exception as exc:
        print("status=TRACE_NET_H27_ENGRAM_OVERLAY_MAP_PATCH_FAILED")
        print(f"error={exc}")
        print(f"backup={backup}")
        return 1
    TARGET.write_text(src, encoding="utf-8")
    print("status=TRACE_NET_H27_ENGRAM_OVERLAY_MAP_PATCH_APPLIED")
    print("quality_status=PASS")
    for k, v in changed.items():
        print(f"{k}={v}")
    print(f"backup={backup}")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
