from __future__ import annotations

from pathlib import Path

TARGET = Path('tiff/page_image_recognition.py')

OLD = '        role = str(ctx.get("role") or row.get("role") or "")\n'
NEW = '''        role = str(\n            ctx.get("role")\n            or ctx.get("page_role")\n            or ctx.get("classification")\n            or ctx.get("primary_role")\n            or row.get("role")\n            or row.get("page_role")\n            or row.get("classification")\n            or ""\n        )\n'''


def main() -> int:
    text = TARGET.read_text(encoding='utf-8')
    if NEW in text:
        print(f'{TARGET} already has robust page-role extraction.')
        return 0
    if OLD not in text:
        raise SystemExit(f'Could not find expected role extraction line in {TARGET}')
    TARGET.write_text(text.replace(OLD, NEW), encoding='utf-8')
    print(f'Patched page role extraction in {TARGET}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
