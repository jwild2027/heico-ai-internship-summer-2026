from types import SimpleNamespace

from tiff import trace_net_ocr_route_scan_pack_v1 as scan


def test_tesseract_output_is_captured_as_bytes_and_decoded_safely(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append({"cmd": cmd, "capture_output": capture_output, "text": text, "timeout": timeout})
        return SimpleNamespace(
            returncode=0,
            stdout=b"Passenger Seats\x9d 120-12345-001",
            stderr=b"warning: odd byte \x9d",
        )

    monkeypatch.setattr(scan.subprocess, "run", fake_run)

    result = scan._run_tesseract_on_bytes(
        b"fake-tiff-bytes",
        suffix=".tif",
        tesseract_cmd="/c/fake/tesseract.exe",
        psm_modes=(3,),
        request_timeout=5,
    )

    assert calls and calls[0]["text"] is False
    assert result["tesseract_execution_status"] == "ok"
    assert "Passenger Seats" in result["best_ocr_text"]
    assert result["best_part_number_tokens"] == ["120-12345-001"]
    assert "warning" in result["tesseract_attempts"][0]["stderr_sample"]
