# TIFF page image-recognition quality fix

Fixes the page image-recognition quality parser so it reads `readable_images` from the audit JSON correctly and keeps the CLI stable.

Run:

```bash
python scripts/check_page_image_recognition_quality.py --write-json
```
