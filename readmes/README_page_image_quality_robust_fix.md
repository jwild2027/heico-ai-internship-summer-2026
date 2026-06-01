# Page image-recognition quality robust parser fix

Replaces `tiff/page_image_recognition_quality.py` with a defensive parser that supports the current page image-recognition audit JSON shape and older test shapes.

It restores the public API names:

- `summarize_page_image_recognition_audit`
- `build_page_image_recognition_quality`
- `build_page_image_recognition_quality_report`
- `page_image_recognition_quality`
- `main`

Expected real-audit values after running the checker:

- `page_image_readable_images: 509`
- `page_image_likely_figure_pages: 493`
- `page_image_likely_table_pages: 331`
- quality status `OK`
