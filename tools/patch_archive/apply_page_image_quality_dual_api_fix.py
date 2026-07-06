from pathlib import Path

TARGET = Path('tiff/page_image_recognition_quality.py')

APPEND = r'''

# Compatibility wrapper: historical callers/tests expect this function to return
# a plain dictionary, while build_page_image_recognition_quality_report returns
# the richer QualityReport object used by the CLI/quality gate.
def _page_image_quality_report_to_dict_compat(report):
    if isinstance(report, dict):
        return report

    status = getattr(report, 'status', None)
    summary = getattr(report, 'summary', None) or {}
    checks = getattr(report, 'checks', None) or []

    normalized_checks = []
    for check in checks:
        if isinstance(check, dict):
            normalized_checks.append(check)
            continue
        item = {}
        for key in ('name', 'status', 'message', 'detail'):
            if hasattr(check, key):
                item[key] = getattr(check, key)
        # Some project QualityCheck variants use different field names.
        for key in ('label', 'reason', 'value'):
            if hasattr(check, key) and key not in item:
                item[key] = getattr(check, key)
        normalized_checks.append(item)

    return {
        'status': status,
        'summary': dict(summary) if hasattr(summary, 'items') else summary,
        'checks': normalized_checks,
    }


def build_page_image_recognition_quality(*args, **kwargs):
    return _page_image_quality_report_to_dict_compat(
        build_page_image_recognition_quality_report(*args, **kwargs)
    )
'''


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f'Missing target: {TARGET}')
    text = TARGET.read_text(encoding='utf-8')
    marker = '# Compatibility wrapper: historical callers/tests expect this function to return'
    if marker in text:
        print(f'{TARGET} already has dual API compatibility wrapper.')
        return 0
    TARGET.write_text(text.rstrip() + APPEND + '\n', encoding='utf-8')
    print(f'Patched {TARGET}: build_page_image_recognition_quality now returns a dict; report function remains object-style.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
