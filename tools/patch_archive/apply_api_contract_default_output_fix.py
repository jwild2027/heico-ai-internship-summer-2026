from pathlib import Path

TARGET = Path('tests/unit/test_tiff_api_contract_tests.py')

def main() -> int:
    if not TARGET.exists():
        print(f'ERROR: {TARGET} not found')
        return 1
    text = TARGET.read_text(encoding='utf-8')
    old = "str(DEFAULT_OUTPUT).replace('\\\\', '/').endswith('local_data/api/api_contract_results.json')"
    new = "str(DEFAULT_OUTPUT).replace('\\\\', '/').replace('\\\\\\\\', '/').endswith('local_data/api/api_contract_results.json')"
    # Simpler final form: normalize every Windows separator to POSIX separators.
    final = "str(DEFAULT_OUTPUT).replace('\\\\', '/').endswith('local_data/api/api_contract_results.json')"
    # If the file currently replaces double backslashes, make it replace single backslashes.
    candidates = [
        "str(DEFAULT_OUTPUT).replace('\\\\\\\\', '/').endswith('local_data/api/api_contract_results.json')",
        "str(DEFAULT_OUTPUT).replace(\"\\\\\\\\\", '/').endswith('local_data/api/api_contract_results.json')",
    ]
    replacement = "str(DEFAULT_OUTPUT).replace('\\\\', '/').endswith('local_data/api/api_contract_results.json')"
    changed = False
    for candidate in candidates:
        if candidate in text:
            text = text.replace(candidate, replacement)
            changed = True
    # Also handle the exact string shown by pytest source display in some shells.
    if "replace('\\\\', '/')" in text:
        # This is already the single-backslash normalization in source; nothing to do.
        pass
    TARGET.write_text(text, encoding='utf-8')
    print(('Patched' if changed else 'No test patch needed') + f': {TARGET}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
