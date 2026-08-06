#!/usr/bin/env python3
"""Repair TRACE-Net H16C incomplete-answer retry hook placement.

v1b could insert the incomplete-answer guard into build_arg_parser because that
function mentions Ollama CLI flags and returns `parser`. This repair removes any
bad parser/args guard and inserts the guard only into the actual Ollama response
helper, identified by real generation-call signals such as api/generate,
urlopen/request, or the H16B empty-output RuntimeError.
"""

from __future__ import annotations

import argparse
import ast
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

TARGET = Path("tiff/trace_net_engineering_llm_answer_smoke_v1.py")
RETURN_MARKER = "H16C_INCOMPLETE_ANSWER_RETURN_GUARD_V1"
BAD_GUARD_RE = re.compile(
    r"^(?P<indent>[ \t]*)if _h16c_looks_incomplete_llm_answer\((?P<bad>parser|ap|args)\):\n"
    r"(?P=indent)[ \t]+raise RuntimeError\(\"Ollama response looked incomplete or truncated\"\)"
    r"[^\n]*\n?",
    re.MULTILINE,
)


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak_h16c_repair_v1_{stamp}")
    shutil.copy2(path, backup)
    return backup


def _remove_bad_parser_guard(text: str) -> Tuple[str, int]:
    return BAD_GUARD_RE.subn("", text)


def _function_spans(text: str) -> List[Tuple[str, int, int]]:
    tree = ast.parse(text)
    spans: List[Tuple[str, int, int]] = []
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", None)
            if end is None:
                end = start + 1
                base_indent = len(lines[start]) - len(lines[start].lstrip())
                while end < len(lines):
                    line = lines[end]
                    stripped = line.strip()
                    if stripped and (len(line) - len(line.lstrip())) <= base_indent and not line.lstrip().startswith("#"):
                        break
                    end += 1
            spans.append((node.name, start, int(end)))
    spans.sort(key=lambda x: x[1])
    return spans


def _simple_return_var(line: str) -> Optional[str]:
    m = re.match(r"^(\s*)return\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
    return m.group(2) if m else None


def _patch_real_ollama_return_guard(text: str) -> Tuple[str, int, str]:
    """Insert guard before return of the real Ollama response helper.

    Excludes build_arg_parser/main and any function that only mentions Ollama in
    CLI argument declarations. Requires real generation-call signals.
    """
    if RETURN_MARKER in text and "_h16c_looks_incomplete_llm_answer(parser)" not in text:
        return text, 0, "already_present"

    lines = text.splitlines()
    spans = _function_spans(text)
    candidates: List[Tuple[int, int, int, str]] = []  # score, start, end, name

    for name, start, end in spans:
        if name in {"build_arg_parser", "main"}:
            continue
        body = "\n".join(lines[start:end])
        lower = body.lower()
        # Real call/output signals, not just argparse flag strings.
        has_generation_signal = any(
            signal in lower
            for signal in (
                "api/generate",
                "urllib.request",
                "urlopen",
                "request(",
                "did not contain answer text",
                "data.get(\"response\"",
                "data.get('response'",
                "payload.get(\"response\"",
                "payload.get('response'",
            )
        )
        if not has_generation_signal:
            continue
        if "argparse.argumentparser" in lower:
            continue

        simple_returns: List[Tuple[int, str]] = []
        for idx in range(start + 1, end):
            var = _simple_return_var(lines[idx])
            if var and var not in {"parser", "ap", "args", "payload", "data", "req"}:
                simple_returns.append((idx, var))
        if not simple_returns:
            continue

        score = 0
        if "did not contain answer text" in lower:
            score -= 100
        if "api/generate" in lower:
            score -= 60
        if "data.get(\"response\"" in lower or "data.get('response'" in lower:
            score -= 40
        if "ollama" in name.lower():
            score -= 25
        score += end - start
        candidates.append((score, start, end, name))

    if not candidates:
        return text, 0, "no_candidate"

    _, start, end, name = sorted(candidates, key=lambda x: x[0])[0]

    return_idx = None
    return_var = None
    for idx in range(end - 1, start, -1):
        var = _simple_return_var(lines[idx])
        if var and var not in {"parser", "ap", "args", "payload", "data", "req"}:
            return_idx = idx
            return_var = var
            break

    if return_idx is None or return_var is None:
        return text, 0, "no_return_var"

    # Avoid double insertion immediately before this return.
    window = "\n".join(lines[max(start, return_idx - 5):return_idx + 1])
    if "Ollama response looked incomplete or truncated" in window:
        return text, 0, f"already_near_return:{name}"

    indent = re.match(r"^(\s*)", lines[return_idx]).group(1)
    guard = [
        f"{indent}if _h16c_looks_incomplete_llm_answer({return_var}):",
        f"{indent}    raise RuntimeError(\"Ollama response looked incomplete or truncated\")  # {RETURN_MARKER}",
    ]
    lines[return_idx:return_idx] = guard
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), 1, f"patched:{name}:{return_var}"


def _verify(text: str) -> List[str]:
    errors: List[str] = []
    if "_h16c_looks_incomplete_llm_answer(parser)" in text:
        errors.append("bad parser incomplete-answer guard still present")
    if "_h16c_merge_ollama_options(" not in text:
        errors.append("missing H16C Ollama option merge hook")
    if "Ollama response looked incomplete or truncated" not in text:
        errors.append("missing H16C incomplete-answer guard in Ollama helper")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=str(TARGET))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        raise SystemExit(f"target file not found: {target}")

    original = target.read_text(encoding="utf-8")
    repaired, bad_removed_count = _remove_bad_parser_guard(original)
    repaired, guard_inserted_count, guard_note = _patch_real_ollama_return_guard(repaired)

    errors = _verify(repaired)
    if errors:
        print("status=TRACE_NET_H16C_INCOMPLETE_RETRY_REPAIR_FAILED")
        for err in errors:
            print("error=" + err)
        print("guard_note=" + guard_note)
        print("hint=run grep -n \"def .*ollama\\|api/generate\\|urlopen\\|did not contain answer text\\|return .*answer\\|return .*response\" tiff/trace_net_engineering_llm_answer_smoke_v1.py | head -120")
        raise SystemExit(1)

    changed = repaired != original
    backup = None
    if changed and not args.dry_run:
        backup = _backup(target)
        target.write_text(repaired, encoding="utf-8", newline="\n")

    print("status=TRACE_NET_H16C_INCOMPLETE_RETRY_REPAIRED")
    print("quality_status=PASS")
    print(f"target={target}")
    print(f"changed={changed}")
    print(f"bad_parser_guard_removed_count={bad_removed_count}")
    print(f"real_ollama_guard_inserted_count={guard_inserted_count}")
    print(f"guard_note={guard_note}")
    if backup:
        print(f"backup={backup}")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")


if __name__ == "__main__":
    main()
