# Manual grouping and ResCarta staging

The TIFF scanner works page-by-page. ResCarta should usually receive a logical
manual object containing many TIFF pages.

This add-on adds a read-only grouping step:

```bash
python scripts/group_tiff_manuals.py \
  --db-path local_data/db/tiff_scans_full.db \
  --output local_data/manual_groups.json \
  --print-summary
```

Then create a staging package:

```bash
python scripts/export_rescarta_staging.py \
  --manifest local_data/manual_groups.json \
  --output-dir local_data/rescarta_exports \
  --copy-pages
```

Output shape:

```text
local_data/rescarta_exports/
└── t_p_120_1176/
    ├── metadata.json
    ├── manifest.json
    ├── pages/
    │   ├── 000001_00000001.tif
    │   └── ...
    └── ocr/
        ├── 000001_00000001.txt
        ├── 000001_00000001.metadata.json
        └── ...
```

This is a staging package, not yet the final ResCarta archive format. The next
step is to manually compare this staging package to ResCarta Toolkit output and
map the fields into ResCarta's object/collection metadata.
