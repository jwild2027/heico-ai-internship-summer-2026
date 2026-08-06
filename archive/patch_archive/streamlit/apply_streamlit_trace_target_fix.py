from __future__ import annotations

from pathlib import Path
import re
import sys

TARGET = Path("apps/streamlit/tiff_api_ui.py")

NEW_BODY = '''def infer_trace_target(question: str, answer_text: str = "") -> dict[str, str]:
    """Infer the safest graph trace target from a user question/answer.

    Detection order matters. ATA codes such as 25-21-00 look part-like
    enough to be caught by broad part-number regexes, so page IDs are
    checked first, ATA codes second, and part numbers last.
    """
    combined = f"{question or ''}\n{answer_text or ''}"

    page_id = find_first_page_id(combined)
    if page_id:
        return {"type": "page", "value": page_id}

    ata_code = find_first_ata(combined)
    if ata_code:
        return {"type": "ata", "value": ata_code}

    part_number = find_first_part(combined)
    if part_number:
        return {"type": "part", "value": part_number}

    return {"type": "none", "value": ""}
'''


def replace_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(rf"^def {re.escape(name)}\s*\([^\n]*\):\n(?:^[ \t].*\n|^\s*$\n?)*", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"Could not find top-level function {name!r} in {TARGET}")
    return text[: match.start()] + replacement + text[match.end():]


def main() -> int:
    if not TARGET.exists():
        print(f"Missing target file: {TARGET}", file=sys.stderr)
        return 2

    original = TARGET.read_text(encoding="utf-8")
    updated = replace_function(original, "infer_trace_target", NEW_BODY)

    if updated == original:
        print("No changes made; infer_trace_target already matched replacement.")
        return 0

    backup = TARGET.with_suffix(TARGET.suffix + ".trace_target_fix.bak")
    backup.write_text(original, encoding="utf-8")
    TARGET.write_text(updated, encoding="utf-8")
    print(f"Patched {TARGET}")
    print(f"Backup written to {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
