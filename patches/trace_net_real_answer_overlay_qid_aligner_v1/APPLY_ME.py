from __future__ import annotations

import re
import shutil
from pathlib import Path

PATCH_NAME = "trace_net_real_answer_overlay_qid_aligner_v1"
ROOT = Path.cwd()
SRC = Path(__file__).resolve().parent / "files"

FILES = [
    "tiff/trace_net_engineering_real_answer_overlay_question_id_aligner_v1.py",
    "scripts/build_trace_net_engineering_real_answer_overlay_question_id_aligner_v1.py",
    "tests/unit/test_trace_net_engineering_real_answer_overlay_question_id_aligner_v1.py",
    "docs/trace_net_engineering_real_answer_overlay_question_id_aligner_v1_README.md",
]


def _copy_file(rel: str) -> None:
    src = SRC / rel
    dst = ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"wrote {rel}")


def _replace_function(lines: list[str], func_name: str, replacement: str) -> list[str]:
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {func_name}("):
            start = i
            break
    if start is None:
        raise SystemExit(f"Could not find {func_name}")
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
    if end is None:
        end = len(lines)
    return lines[:start] + replacement.splitlines(True) + lines[end:]


def _ensure_context_pack_builder_contract() -> None:
    path = ROOT / "tiff/trace_net_engineering_answer_runner_overlay_context_pack_v1.py"
    if not path.exists():
        raise SystemExit(f"Missing expected file: {path}")

    backup = path.with_suffix(path.suffix + ".bak_qid_aligner_v1")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"backup {backup.relative_to(ROOT)}")

    text = path.read_text(encoding="utf-8")

    # Keep write helpers Windows-safe and parent-directory-safe.
    lines = text.splitlines(True)
    write_json_replacement = '''def _write_json(path: Path, data: Mapping[str, Any]) -> None:\n    path = Path(path)\n    path.parent.mkdir(parents=True, exist_ok=True)\n    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")\n\n\n'''
    write_jsonl_replacement = '''def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:\n    path = Path(path)\n    path.parent.mkdir(parents=True, exist_ok=True)\n    with path.open("w", encoding="utf-8") as f:\n        for row in rows:\n            f.write(json.dumps(dict(row), sort_keys=True) + "\\n")\n\n\n'''
    lines = _replace_function(lines, "_write_json", write_json_replacement)
    lines = _replace_function(lines, "_write_jsonl", write_jsonl_replacement)
    text = "".join(lines)

    # Ensure the child CLI accepts --min-matched-overlays exactly once.
    parser_line_re = re.compile(r'^\s*p\.add_argument\(["\']--min-matched-overlays["\'].*\n', re.MULTILINE)
    text = parser_line_re.sub("", text)
    min_records_patterns = [
        '    p.add_argument("--min-records", type=int, default=1)\n',
        "    p.add_argument('--min-records', type=int, default=1)\n",
    ]
    for target in min_records_patterns:
        if target in text:
            quote = '"' if '"' in target else "'"
            text = text.replace(
                target,
                target + f"    p.add_argument({quote}--min-matched-overlays{quote}, type=int, default=0)\n",
                1,
            )
            break
    else:
        raise SystemExit("Could not find --min-records parser line in context-pack builder")

    # Ensure the builder function can receive min_matched_overlays.
    sig_match = re.search(r'def build_overlay_context_pack_manifest\((.*?)\) -> Dict\[str, Any\]:', text, re.S)
    if not sig_match:
        sig_match = re.search(r'def build_overlay_context_pack_manifest\((.*?)\):', text, re.S)
    if not sig_match:
        raise SystemExit("Could not find build_overlay_context_pack_manifest signature")
    sig_text = sig_match.group(0)
    if "min_matched_overlays" not in sig_text:
        new_sig = sig_text
        if "max_write_attempts" in new_sig:
            new_sig = re.sub(
                r'(\n\s*max_write_attempts:\s*int\s*=\s*0,?)',
                r'\1\n    min_matched_overlays: int = 0,',
                new_sig,
                count=1,
            )
        elif "min_records" in new_sig:
            new_sig = re.sub(
                r'(\n\s*min_records:\s*int\s*=\s*1,?)',
                r'\1\n    min_matched_overlays: int = 0,',
                new_sig,
                count=1,
            )
        else:
            new_sig = new_sig.replace(") ->", "\n    min_matched_overlays: int = 0,\n) ->", 1)
        text = text.replace(sig_text, new_sig, 1)

    # Ensure main() passes the CLI arg into the builder.
    main_pos = text.find("def main(")
    call_pos = text.find("build_overlay_context_pack_manifest(", main_pos)
    if call_pos == -1:
        raise SystemExit("Could not find build_overlay_context_pack_manifest call in main")
    call_end = text.find(")", call_pos)
    call_text = text[call_pos:call_end]
    if "min_matched_overlays=" not in call_text:
        if "min_records=args.min_records," in call_text:
            text = text.replace(
                "        min_records=args.min_records,\n",
                "        min_records=args.min_records,\n        min_matched_overlays=args.min_matched_overlays,\n",
                1,
            )
        elif "max_write_attempts=args.max_write_attempts," in call_text:
            text = text.replace(
                "        max_write_attempts=args.max_write_attempts,\n",
                "        max_write_attempts=args.max_write_attempts,\n        min_matched_overlays=args.min_matched_overlays,\n",
                1,
            )
        else:
            raise SystemExit("Could not find safe insertion point for min_matched_overlays call arg")

    # Ensure quality gate enforces the threshold when requested.
    if "matched_overlay_count_below_min" not in text:
        status_match = re.search(r'^\s*quality_status\s*=\s*["\']PASS["\']\s+if\s+not\s+quality_failures\s+else\s+["\']FAIL["\'].*$', text, re.MULTILINE)
        if not status_match:
            raise SystemExit("Could not find quality_status assignment in context-pack builder")
        indent = status_match.group(0)[: len(status_match.group(0)) - len(status_match.group(0).lstrip())]
        gate = (
            f"{indent}if matched_overlay_count < min_matched_overlays:\n"
            f"{indent}    quality_failures.append(f\"matched_overlay_count_below_min:{{matched_overlay_count}}<{{min_matched_overlays}}\")\n"
        )
        text = text[: status_match.start()] + gate + text[status_match.start():]

    # Add summary field when possible.
    if '"min_matched_overlays"' not in text and '"matched_overlay_count": matched_overlay_count,' in text:
        text = text.replace(
            '        "matched_overlay_count": matched_overlay_count,\n',
            '        "matched_overlay_count": matched_overlay_count,\n        "min_matched_overlays": min_matched_overlays,\n',
            1,
        )

    path.write_text(text, encoding="utf-8")
    print("patched tiff/trace_net_engineering_answer_runner_overlay_context_pack_v1.py")


def main() -> int:
    for rel in FILES:
        _copy_file(rel)
    _ensure_context_pack_builder_contract()
    print(f"PATCH_APPLIED {PATCH_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
