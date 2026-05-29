# API adapter ATA source fix

Fixes a compatibility issue in `tiff/storage_adapters.py` where ATA entries can store page references as page-id strings, while `_page_source_from_page()` expected a page dictionary.

Run:

```bash
python scripts/apply_storage_adapter_ata_source_fix.py
python -m pytest tests/unit/test_tiff_storage_adapters.py tests/unit/test_tiff_api_adapter_services.py -q
```
