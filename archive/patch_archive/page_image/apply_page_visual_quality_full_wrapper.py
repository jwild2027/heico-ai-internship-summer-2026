#!/usr/bin/env python
from __future__ import annotations

from pathlib import Path

TARGET = Path("scripts/maintenance/benchmark/check_full_system_quality.py")


def main() -> int:
    if not TARGET.exists():
        print(f"Missing {TARGET}; skipping wrapper patch")
        return 0
    text = TARGET.read_text(encoding="utf-8")
    changed = False
    if "--require-page-visual-object-quality" not in text:
        needle = '    parser.add_argument("--require-source-package-traceability", action="store_true")\n'
        repl = needle + '    parser.add_argument("--require-page-visual-object-quality", action="store_true")\n'
        if needle in text:
            text = text.replace(needle, repl, 1)
            changed = True
        else:
            print("Could not find parser flag insertion point; flag not added")
    if "Page visual/object quality requirement" not in text:
        needle = "    return exit_code\n"
        block = (
            "    if getattr(args, \"require_page_visual_object_quality\", False):\n"
            "        exit_code = max(exit_code, _print_extra_requirement(\"Page visual/object quality requirement\", ROOT / \"local_data/organization/page_visual_object_quality.json\"))\n"
            "\n"
            "    return exit_code\n"
        )
        if needle in text:
            text = text.replace(needle, block, 1)
            changed = True
        else:
            print("Could not find return insertion point; requirement not added")
    if changed:
        TARGET.write_text(text, encoding="utf-8")
        print(f"Patched {TARGET} with page visual/object quality requirement")
    else:
        print(f"{TARGET} already includes page visual/object quality requirement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
