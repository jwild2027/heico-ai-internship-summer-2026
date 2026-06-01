from pathlib import Path

from tiff.server_access_runbook import build_server_access_runbook, render_markdown, write_runbook_files


def test_build_server_access_runbook_has_required_sections() -> None:
    report = build_server_access_runbook(server_root="/srv/tiff", target_total_tb=5, max_files=1000, pilot_pages=50)
    assert report["status"] == "OK"
    assert report["server_root"] == "/srv/tiff"
    assert report["max_inventory_files"] == 1000
    sections = {item["section"] for item in report["checklist"]}
    assert "Access and permissions" in sections
    assert "OCR availability" in sections
    assert "ResCarta/source links" in sections
    assert "Production storage" in sections
    commands = "\n".join(step["command"] for step in report["runbook_steps"])
    assert "audit_real_server_inventory.py" in commands
    assert "audit_ocr_depth.py" in commands
    assert "run_ocr_pilot.py" in commands


def test_render_markdown_mentions_guardrails_and_commands() -> None:
    report = build_server_access_runbook(server_root="<ROOT>")
    markdown = render_markdown(report)
    assert "# TIFF Real-Server Access Checklist" in markdown
    assert "Do not run OCR" in markdown
    assert "audit_real_server_inventory.py" in markdown
    assert "metadata" in markdown.lower()


def test_write_runbook_files(tmp_path: Path) -> None:
    report = build_server_access_runbook(server_root="/server/root")
    json_output = tmp_path / "server_access.json"
    md_output = tmp_path / "server_access.md"
    write_runbook_files(report, json_output=json_output, markdown_output=md_output)
    assert json_output.exists()
    assert md_output.exists()
    assert "server_root" in json_output.read_text(encoding="utf-8")
    assert "First-access runbook" in md_output.read_text(encoding="utf-8")
