#!/usr/bin/env python3
"""Apply TRACE-Net H16C incomplete-answer retry hooks to the local smoke module.

Repair edition v1b: this patcher is more flexible than the first H16C patcher.
It does not require the H16B empty-response RuntimeError to be next to a very
specific `if not answer_text:` shape. Instead it finds the Ollama response helper
function by content and inserts the incomplete-answer guard immediately before the
function returns model text.
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
MARKER = "H16C_INCOMPLETE_ANSWER_RETRY_V1"
RETURN_MARKER = "H16C_INCOMPLETE_ANSWER_RETURN_GUARD_V1"
PAYLOAD_MARKER = "H16C_INCOMPLETE_ANSWER_OPTIONS_V1"

IMPORT_BLOCK = '''
# H16C_INCOMPLETE_ANSWER_RETRY_V1: generation reliability helpers for local Ollama smoke tests.
try:
    from tiff.trace_net_h16c_llm_answer_reliability_v1 import (
        looks_incomplete_llm_answer as _h16c_looks_incomplete_llm_answer,
        merge_h16c_ollama_options as _h16c_merge_ollama_options,
    )
except Exception:  # pragma: no cover - fallback keeps older local test envs import-safe.
    def _h16c_looks_incomplete_llm_answer(text, require_sections=True, min_chars=350):
        s = (text or "").strip()
        if not s:
            return True
        lowered = " ".join(s.split()).lower()
        if len(lowered) < int(min_chars):
            return True
        tails = (
            " which allows the system to", " which allows trace-net to",
            " allows the system to", " can then carry this ocr-backed",
            " this ocr-backed", " ocr-backed", " because", " and", " or",
            " to", " with", " while", " that", " which", ",", ":", ";", "-",
        )
        if lowered[-160:].rstrip().endswith(tails):
            return True
        if require_sections:
            required = ("answer", "evidence", "engineering confidence", "limits")
            if any(x not in lowered for x in required):
                return True
        return False

    def _h16c_merge_ollama_options(payload):
        options = payload.setdefault("options", {})
        if not isinstance(options, dict):
            options = {}
            payload["options"] = options
        options.setdefault("num_predict", 900)
        options.setdefault("temperature", 0.1)
        return payload
# /H16C_INCOMPLETE_ANSWER_RETRY_V1
'''


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak_{MARKER.lower()}_{stamp}")
    shutil.copy2(path, backup)
    return backup


def _insert_import_block(text: str) -> Tuple[str, bool]:
    if MARKER in text:
        return text, False
    lines = text.splitlines()
    insert_at = 0
    last_import = -1
    for i, line in enumerate(lines[:160]):
        if line.startswith("import ") or line.startswith("from "):
            last_import = i
    if last_import >= 0:
        insert_at = last_import + 1
    lines[insert_at:insert_at] = IMPORT_BLOCK.strip("\n").splitlines()
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), True


def _find_payload_blocks(lines: List[str]) -> List[Tuple[int, int, str]]:
    blocks: List[Tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{\s*$", line)
        if not m:
            continue
        var = m.group(2)
        depth = 0
        contains_stream_false = False
        contains_model_or_prompt = False
        contains_ollama_hint = False
        for j in range(i, min(len(lines), i + 120)):
            current = lines[j]
            depth += current.count("{") - current.count("}")
            if re.search(r"['\"]stream['\"]\s*:\s*False", current):
                contains_stream_false = True
            if re.search(r"['\"]model['\"]\s*:", current) or re.search(r"['\"]prompt['\"]\s*:", current):
                contains_model_or_prompt = True
            if "ollama" in current.lower() or "api/generate" in current.lower():
                contains_ollama_hint = True
            if depth <= 0 and j > i:
                if contains_stream_false and contains_model_or_prompt:
                    blocks.append((i, j, var))
                break
    return blocks


def _patch_payload_options(text: str) -> Tuple[str, int]:
    if PAYLOAD_MARKER in text or "avoid truncated local Ollama answers" in text:
        return text, 0
    lines = text.splitlines()
    blocks = _find_payload_blocks(lines)
    patches = 0
    offset = 0
    for start, end, var in blocks:
        idx = end + 1 + offset
        indent = re.match(r"^(\s*)", lines[start + offset]).group(1)
        lines.insert(idx, f"{indent}_h16c_merge_ollama_options({var})  # {PAYLOAD_MARKER}: avoid truncated local Ollama answers")
        offset += 1
        patches += 1
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), patches


def _function_spans(text: str) -> List[Tuple[str, int, int]]:
    """Return (function_name, start_line_idx, end_line_idx_exclusive)."""
    tree = ast.parse(text)
    spans: List[Tuple[str, int, int]] = []
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", None)
            if end is None:
                # Fallback for old Python ASTs; this environment should have end_lineno.
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


def _patch_return_guard_by_function(text: str) -> Tuple[str, int]:
    if RETURN_MARKER in text or "Ollama response looked incomplete or truncated" in text:
        return text, 0

    lines = text.splitlines()
    spans = _function_spans(text)
    candidate_spans: List[Tuple[str, int, int]] = []

    for name, start, end in spans:
        body = "\n".join(lines[start:end])
        lower = body.lower()
        # Find the function that actually calls Ollama or validates Ollama output.
        if (
            "ollama" in lower
            or "api/generate" in lower
            or "did not contain answer text" in lower
            or "urllib.request" in lower and "response" in lower
        ):
            if re.search(r"\breturn\s+[A-Za-z_][A-Za-z0-9_]*\s*$", body, re.MULTILINE):
                candidate_spans.append((name, start, end))

    if not candidate_spans:
        return text, 0

    # Prefer the smallest function that contains the empty-output error, then any Ollama helper.
    def score(span: Tuple[str, int, int]) -> Tuple[int, int]:
        name, start, end = span
        body = "\n".join(lines[start:end]).lower()
        priority = 0
        if "did not contain answer text" in body:
            priority -= 100
        if "api/generate" in body:
            priority -= 50
        if "ollama" in name.lower():
            priority -= 25
        return (priority, end - start)

    name, start, end = sorted(candidate_spans, key=score)[0]

    # Patch the last simple return in the candidate function.
    return_idx = None
    return_var = None
    for i in range(end - 1, start, -1):
        var = _simple_return_var(lines[i])
        if var:
            return_idx = i
            return_var = var
            break
    if return_idx is None or return_var is None:
        return text, 0

    indent = re.match(r"^(\s*)", lines[return_idx]).group(1)
    guard = [
        f"{indent}if _h16c_looks_incomplete_llm_answer({return_var}):",
        f"{indent}    raise RuntimeError(\"Ollama response looked incomplete or truncated\")  # {RETURN_MARKER}",
    ]
    lines[return_idx:return_idx] = guard
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), 1


def _patch_raise_adjacent_fallback(text: str) -> Tuple[str, int]:
    """Fallback: if function-span patch missed, insert after the empty-output raise."""
    if RETURN_MARKER in text or "Ollama response looked incomplete or truncated" in text:
        return text, 0
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "Ollama response did not contain answer text" not in line:
            continue
        raise_indent = len(line) - len(line.lstrip())
        block_indent = max(0, raise_indent - 4)
        # Choose likely answer variable from nearby assignment / return context.
        nearby = "\n".join(lines[max(0, i - 20): min(len(lines), i + 20)])
        candidates = []
        for pat in [
            r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\(?\s*data\.get\(['\"]response['\"]",
            r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\(?\s*payload\.get\(['\"]response['\"]",
            r"return\s+([A-Za-z_][A-Za-z0-9_]*)",
        ]:
            candidates += re.findall(pat, nearby)
        var = candidates[-1] if candidates else "answer_text"
        indent = " " * block_indent
        insert_at = i + 1
        lines[insert_at:insert_at] = [
            f"{indent}if _h16c_looks_incomplete_llm_answer({var}):",
            f"{indent}    raise RuntimeError(\"Ollama response looked incomplete or truncated\")  # {RETURN_MARKER}",
        ]
        return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), 1
    return text, 0


def _verify(text: str) -> List[str]:
    errors: List[str] = []
    if MARKER not in text:
        errors.append("missing H16C marker import/fallback block")
    if "_h16c_merge_ollama_options(" not in text:
        errors.append("missing H16C Ollama option merge hook")
    if RETURN_MARKER not in text and "Ollama response looked incomplete or truncated" not in text:
        errors.append("missing H16C incomplete-answer retry guard")
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
    patched, import_changed = _insert_import_block(original)
    patched, payload_patch_count = _patch_payload_options(patched)
    patched, guard_patch_count = _patch_return_guard_by_function(patched)
    if guard_patch_count == 0:
        patched, guard_patch_count = _patch_raise_adjacent_fallback(patched)

    errors = _verify(patched)
    if errors:
        print("status=TRACE_NET_H16C_INCOMPLETE_RETRY_PATCH_FAILED")
        for err in errors:
            print("error=" + err)
        print("hint=run grep -n \"Ollama response\|api/generate\|return .*answer\|return .*response\" tiff/trace_net_engineering_llm_answer_smoke_v1.py | head -80")
        raise SystemExit(1)

    changed = patched != original
    backup = None
    if changed and not args.dry_run:
        backup = _backup(target)
        target.write_text(patched, encoding="utf-8", newline="\n")

    print("status=TRACE_NET_H16C_INCOMPLETE_RETRY_PATCH_APPLIED")
    print("quality_status=PASS")
    print(f"target={target}")
    print(f"changed={changed}")
    print(f"import_block_inserted={import_changed}")
    print(f"payload_option_hook_count={payload_patch_count}")
    print(f"incomplete_retry_guard_count={guard_patch_count}")
    if backup:
        print(f"backup={backup}")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")


if __name__ == "__main__":
    main()
