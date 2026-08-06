from tiff.ocr_pilot_progress import _format_duration


def test_format_duration_seconds():
    assert _format_duration(3.2) == "3s"


def test_format_duration_minutes():
    assert _format_duration(65) == "1m 5s"


def test_format_duration_hours():
    assert _format_duration(3661) == "1h 1m 1s"
