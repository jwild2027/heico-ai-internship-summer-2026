# Page image-recognition quality object compatibility fix

Replaces `tiff/page_image_recognition_quality.py` with a compatibility module that:

- restores all public function names used by tests/scripts
- returns `QualityReport` and `QualityCheck` objects with `.status` / `.name`
- parses the current image-recognition audit JSON shape
- counts graph overlay nodes/edges from the paths inside the audit JSON
- exposes `main()` for `scripts/check_page_image_recognition_quality.py`
