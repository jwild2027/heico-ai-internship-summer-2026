# TIFF API adapter refactor compatibility fix

Restores the adapter names expected by existing tests/scripts while preserving the new API -> service -> adapter architecture.

Restored/compatible exports include:

- `LocalArtifactCatalogStore`
- `build_local_store_bundle`
- `adapter_readiness`
- local trace/answer/feedback/quality placeholder stores

Run:

```bash
python -m pytest tests/unit/test_tiff_storage_adapters.py tests/unit/test_tiff_api_adapter_services.py -q
python scripts/check_tiff_storage_adapters.py --write-json
```
