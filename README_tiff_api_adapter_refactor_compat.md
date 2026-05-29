# TIFF API Adapter Refactor Compatibility Patch

Restores backward-compatible storage adapter symbols used by earlier tests/scripts while keeping the new FastAPI service-layer refactor.

Run:

```bash
python -m pytest tests/unit/test_tiff_storage_adapters.py tests/unit/test_tiff_api_adapter_services.py -q
python scripts/check_tiff_storage_adapters.py --write-json
```
