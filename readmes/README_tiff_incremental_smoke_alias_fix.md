# Incremental smoke alias fix

This patch fixes the changed-page smoke test config builder.

`IncrementalPipelineConfig` has current field names and older alias names. The
smoke test previously overrode only the current names, then `__post_init__()`
restored the old alias values from `local_config.yaml`. That made the smoke test
scan the real sample TIFF root instead of the temporary one-file root.

The fix passes both current fields and aliases:

- `tiff_root` and `root`
- `state_db` and `state_db_path`
- `changed_list` and `changed_list_path`
- `scan_db` and `scan_db_path`
- `db_path` and `search_db_path`

After this patch the smoke test should detect exactly one changed TIFF and use
`scripts/update_changed_page_backend.py`, not the full backend rebuild.
