#!/usr/bin/env python3
"""Full-system quality wrapper.

This wrapper runs the base pipeline quality gate and optional side quality gates
for API/adapters, API contracts, page visual/object profile, and page image
recognition. Unknown/base flags are forwarded to scripts/check_pipeline_quality.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXTENDED_FLAGS = {
    "--require-api-adapter-quality": "scripts/check_api_adapter_quality.py",
    "--require-api-contract-tests": "scripts/check_api_contract_quality.py",
    "--require-page-visual-object-quality": "scripts/check_page_visual_object_quality.py",
    "--require-page-image-recognition-quality": "scripts/check_page_image_recognition_quality.py",
}


def _run(cmd: list[str]) -> int:
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    required_scripts: list[str] = []
    base_args: list[str] = []
    for arg in args:
        if arg in EXTENDED_FLAGS:
            required_scripts.append(EXTENDED_FLAGS[arg])
        else:
            base_args.append(arg)

    failures = 0
    base_script = Path("scripts/check_pipeline_quality.py")
    if not base_script.exists():
        print(f"Missing base quality script: {base_script}")
        return 2
    failures += 1 if _run([sys.executable, str(base_script), *base_args]) != 0 else 0

    labels = {
        "scripts/check_api_adapter_quality.py": "API/adapter quality requirement",
        "scripts/check_api_contract_quality.py": "API contract quality requirement",
        "scripts/check_page_visual_object_quality.py": "Page visual/object quality requirement",
        "scripts/check_page_image_recognition_quality.py": "Page image-recognition quality requirement",
    }
    for script in required_scripts:
        print(f"\n{labels.get(script, script)}")
        path = Path(script)
        if not path.exists():
            print(f"  Status: FAIL\n  Missing script: {path}")
            failures += 1
            continue
        rc = _run([sys.executable, str(path), "--write-json"])
        if rc != 0:
            failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
