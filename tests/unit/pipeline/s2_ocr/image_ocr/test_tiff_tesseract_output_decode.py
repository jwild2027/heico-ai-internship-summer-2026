from tiff.title_block_ocr import _decode_tesseract_output


def test_decode_tesseract_output_handles_invalid_windows_bytes():
    raw = b"good text \x9d still here"
    decoded = _decode_tesseract_output(raw)
    assert "good text" in decoded
    assert "still here" in decoded


def test_decode_tesseract_output_accepts_none_and_str():
    assert _decode_tesseract_output(None) == ""
    assert _decode_tesseract_output("already text") == "already text"
