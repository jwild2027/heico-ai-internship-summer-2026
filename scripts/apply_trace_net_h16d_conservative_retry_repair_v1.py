#!/usr/bin/env python3
"""Apply H16D conservative reliability repair for TRACE-Net Engram smoke.

H16D intentionally rolls back the aggressive H16C incomplete-answer hook that
pushed many normal answers into retry/fallback. It restores the pre-H16C smoke
module from the automatic H16C backup when available, then applies only a small
Ollama generation-budget option. This keeps H16B behavior while reducing q18
mid-sentence truncation risk.
"""

from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

TARGET = Path("tiff/trace_net_engineering_llm_answer_smoke_v1.py")
PRE_H16C_BACKUP_GLOB = "trace_net_engineering_llm_answer_smoke_v1.py.bak_h16c_incomplete_answer_retry_v1_*"
OPTION_MARKER = "H16D_CONSERVATIVE_OLLAMA_OPTIONS_V1"


def _backup(path: Path, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak_{label}_{stamp}")
    shutil.copy2(path, backup)
    return backup


def _find_pre_h16c_backup(target: Path) -> Path | None:
    candidates = sorted(target.parent.glob(PRE_H16C_BACKUP_GLOB), key=lambda p: p.stat().st_mtime)
    if not candidates:
        return None
    # Use the oldest H16C backup: it is the clean state before the first H16C mutation.
    return candidates[0]


def _remove_h16c_incomplete_calls(text: str) -> Tuple[str, int]:
    """Remove any if-block that calls _h16c_looks_incomplete_llm_answer.

    This is a fallback cleanup for repos where the pre-H16C backup is absent.
    """
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    i = 0
    removed = 0
    while i < len(lines):
        line = lines[i]
        if "if _h16c_looks_incomplete_llm_answer(" in line:
            removed += 1
            base_indent = len(line) - len(line.lstrip(" "))
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    i += 1
                    continue
                indent = len(nxt) - len(nxt.lstrip(" "))
                if indent <= base_indent:
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return "".join(out), removed


def _remove_h16c_import_block(text: str) -> Tuple[str, int]:
    patterns = [
        re.compile(
            r"\n?try:\n\s+from tiff\.trace_net_h16c_llm_answer_reliability_v1 import[\s\S]*?\n\s+def _h16c_looks_incomplete_llm_answer\([\s\S]*?\n\s+return False\n",
            re.MULTILINE,
        ),
        re.compile(
            r"\n?from tiff\.trace_net_h16c_llm_answer_reliability_v1 import[^\n]*\n",
            re.MULTILINE,
        ),
    ]
    count = 0
    out = text
    for pat in patterns:
        out, n = pat.subn("\n", out)
        count += n
    return out, count


def _patch_ollama_options(text: str) -> Tuple[str, int, str]:
    """Add a conservative Ollama options block to the API payload.

    The patch is intentionally simple and reversible. It does not add incomplete
    answer exceptions. It only gives the local model enough generation budget to
    avoid q18-style mid-sentence cutoff.
    """
    if OPTION_MARKER in text:
        return text, 0, "already_present"

    # If earlier H16C option merge exists, remove it. We want direct, readable
    # options and no dependency on H16C helper imports.
    text, merge_count = re.subn(
        r"\n\s*payload\s*=\s*_h16c_merge_ollama_options\(payload\)\s*\n",
        "\n",
        text,
    )

    # Multi-line common case: insert after stream: False inside payload dict.
    stream_re = re.compile(r"(?P<indent>\s*)[\"']stream[\"']\s*:\s*False\s*,(?P<trail>\s*(?:#.*)?\n)")
    matches = list(stream_re.finditer(text))
    if matches:
        # Choose the first stream=False occurrence near an Ollama payload.
        chosen = None
        for m in matches:
            window = text[max(0, m.start() - 500):m.end() + 500].lower()
            if "model" in window and "prompt" in window:
                chosen = m
                break
        if chosen is None:
            chosen = matches[0]
        insert = (
            chosen.group(0)
            + f"{chosen.group('indent')}\"options\": {{\"num_predict\": 900, \"temperature\": 0.1}},  # {OPTION_MARKER}\n"
        )
        text = text[:chosen.start()] + insert + text[chosen.end():]
        return text, 1, f"inserted_after_stream_false;removed_merge_hooks={merge_count}"

    # One-line payload fallback: add options before final brace for a dict with stream False.
    one_line_re = re.compile(r"payload\s*=\s*\{(?P<body>[^\n{}]*[\"']stream[\"']\s*:\s*False[^\n{}]*)\}")
    m = one_line_re.search(text)
    if m:
        body = m.group("body").rstrip()
        replacement = f"payload = {{{body}, 'options': {{'num_predict': 900, 'temperature': 0.1}}}}  # {OPTION_MARKER}"
        text = text[:m.start()] + replacement + text[m.end():]
        return text, 1, f"inserted_one_line_payload;removed_merge_hooks={merge_count}"

    return text, 0, f"no_payload_stream_false_found;removed_merge_hooks={merge_count}"


def _verify(text: str) -> List[str]:
    errors: List[str] = []
    if "_h16c_looks_incomplete_llm_answer(" in text:
        errors.append("aggressive H16C incomplete-answer calls still present")
    if "_h16c_merge_ollama_options(" in text:
        errors.append("H16C option merge call still present")
    if OPTION_MARKER not in text:
        errors.append("missing H16D conservative Ollama options marker")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=str(TARGET))
    ap.add_argument("--no-restore-backup", action="store_true", help="Do not restore the pre-H16C backup; cleanup current file in place.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        raise SystemExit(f"target file not found: {target}")

    original = target.read_text(encoding="utf-8")
    pre_h16c = None if args.no_restore_backup else _find_pre_h16c_backup(target)
    source_text = original
    restored_from_backup = False
    if pre_h16c is not None:
        source_text = pre_h16c.read_text(encoding="utf-8")
        restored_from_backup = True

    repaired, removed_call_count = _remove_h16c_incomplete_calls(source_text)
    repaired, removed_import_count = _remove_h16c_import_block(repaired)
    repaired, option_insert_count, option_note = _patch_ollama_options(repaired)

    errors = _verify(repaired)
    if errors:
        print("status=TRACE_NET_H16D_CONSERVATIVE_REPAIR_FAILED")
        for err in errors:
            print("error=" + err)
        print(f"restored_from_backup={restored_from_backup}")
        print(f"pre_h16c_backup={pre_h16c or ''}")
        print(f"option_note={option_note}")
        print("hint=run grep -n \"_h16c_looks_incomplete_llm_answer\\|_h16c_merge_ollama_options\\|stream\\|payload\" tiff/trace_net_engineering_llm_answer_smoke_v1.py | head -120")
        return 1

    changed = repaired != original
    backup = None
    if changed and not args.dry_run:
        backup = _backup(target, "h16d_conservative_repair_v1_before")
        target.write_text(repaired, encoding="utf-8", newline="\n")

    print("status=TRACE_NET_H16D_CONSERVATIVE_REPAIR_APPLIED")
    print("quality_status=PASS")
    print(f"target={target}")
    print(f"changed={changed}")
    print(f"restored_from_backup={restored_from_backup}")
    print(f"pre_h16c_backup={pre_h16c or ''}")
    print(f"removed_incomplete_call_count={removed_call_count}")
    print(f"removed_h16c_import_count={removed_import_count}")
    print(f"option_insert_count={option_insert_count}")
    print(f"option_note={option_note}")
    if backup:
        print(f"backup={backup}")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
