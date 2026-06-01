# API contract DEFAULT_OUTPUT test path fix

Run:

```bash
python scripts/apply_api_contract_default_output_fix.py
python -m pytest tests/unit/test_tiff_api_contract_tests.py -q
```

This normalizes the test assertion for Windows path separators.
