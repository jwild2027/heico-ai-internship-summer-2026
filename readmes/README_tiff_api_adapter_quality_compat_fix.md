# API/Adapter Quality Probe Compatibility Fix

This patch fixes the API/adapter quality gate so it accepts both machine-readable
probe dictionaries and current human-readable probe strings such as:

```text
120-37313-001 | ok | pages=28 | name=HOLDER, MAGAZINE
```

Run:

```bash
python -m pytest tests/unit/test_tiff_api_adapter_quality.py -q
python scripts/check_tiff_api_ready.py --write-json
python scripts/check_tiff_storage_adapters.py --write-json
python scripts/check_api_adapter_quality.py --write-json
python scripts/refresh_api_adapter_quality_summary.py
```
