from __future__ import annotations

from pathlib import Path

TARGET = Path("scripts/maintenance/benchmark/check_full_system_quality.py")
BACKUP = Path("scripts/check_full_system_quality_base.py")
FLAG = "--require-page-image-recognition-quality"

WRAPPER = r'''from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts" / "check_full_system_quality_base.py"
IMAGE_QUALITY = ROOT / "scripts/maintenance/ingestion/check_page_image_recognition_quality.py"


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, text=True)
    return int(proc.returncode)


def main() -> int:
    args = sys.argv[1:]
    require_image = "--require-page-image-recognition-quality" in args
    passthrough = [arg for arg in args if arg != "--require-page-image-recognition-quality"]

    if not BASE.exists():
        print(f"Base full-system quality script not found: {BASE}", file=sys.stderr)
        return 1

    status = _run([sys.executable, str(BASE), *passthrough])

    if require_image:
        print()
        print("Page image-recognition quality requirement")
        image_status = _run([sys.executable, str(IMAGE_QUALITY), "--write-json"])
        if image_status != 0:
            status = image_status

    return status


if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    if not TARGET.exists():
        print(f"Missing {TARGET}; nothing patched")
        return 1
    text = TARGET.read_text(encoding="utf-8")
    if FLAG in text or (BACKUP.exists() and "check_full_system_quality_base.py" in text):
        print(f"{TARGET} already includes page image-recognition quality requirement")
        return 0
    BACKUP.write_text(text, encoding="utf-8")
    TARGET.write_text(WRAPPER, encoding="utf-8")
    print(f"Wrapped {TARGET} with page image-recognition quality support")
    print(f"Base script saved to {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
