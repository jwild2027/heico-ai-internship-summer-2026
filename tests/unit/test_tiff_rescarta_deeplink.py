from __future__ import annotations

import sqlite3

import pytest

from tiff.rescarta_deeplink import (
    DEFAULT_TEMPLATE,
    ResCartaTemplateError,
    SourceLinkRow,
    build_tokens,
    is_placeholder_url,
    preview_links,
    render_url,
    update_source_link_urls,
    validate_template,
)


def sample_row() -> SourceLinkRow:
    return SourceLinkRow(
        page_id="t_p_120_1176_p000042",
        manual_id="t_p_120_1176",
        manual_title="T.P. 120/1176",
        ata_code="11-00-66",
        page_label="1021",
        tiff_path="local_data/rescarta_exports/t_p_120_1176/pages/000042_00000042.tif",
        ocr_path="local_data/rescarta_exports/t_p_120_1176/ocr/000042_00000042.txt",
        current_rescarta_url="http://localhost:8080/rescarta/t_p_120_1176/000042",
    )


def test_build_tokens_extracts_page_and_object_aliases():
    tokens = build_tokens(sample_row(), "https://rescarta.example.org/ResCarta-Web")
    assert tokens["object_id"] == "t_p_120_1176"
    assert tokens["page_id"] == "000042"
    assert tokens["page_name"] == "00000042"
    assert tokens["page_id_raw"] == "t_p_120_1176_p000042"
    assert tokens["manual_slug"] == "t_p_120_1176"


def test_render_default_template():
    url = render_url(DEFAULT_TEMPLATE, sample_row(), "https://rescarta.example.org/ResCarta-Web/")
    assert url == "https://rescarta.example.org/ResCarta-Web/jsp/RcWebImageViewer.jsp?doc_id=t_p_120_1176/000042"


def test_render_common_page_name_template():
    template = "{base_url}/jsp/RcWebImageViewer.jsp?doc_id={object_id}&page_name={page_name}"
    url = render_url(template, sample_row(), "https://rescarta.example.org/ResCarta-Web")
    assert "doc_id=t_p_120_1176" in url
    assert "page_name=00000042" in url


def test_template_validation_rejects_unknown_field():
    with pytest.raises(ResCartaTemplateError):
        validate_template("{base_url}/view/{unknown}")


def test_placeholder_detection():
    assert is_placeholder_url("http://localhost:8080/rescarta/x/y") is True
    assert is_placeholder_url("https://rescarta.company.example/ResCarta-Web/jsp/RcWebImageViewer.jsp") is False


def test_preview_links_returns_current_and_proposed():
    previews = preview_links([sample_row().__dict__], DEFAULT_TEMPLATE, "https://rescarta.example.org/ResCarta-Web")
    assert previews[0]["current_rescarta_url"].startswith("http://localhost")
    assert previews[0]["proposed_rescarta_url"].startswith("https://rescarta.example.org")


def test_update_source_link_urls_updates_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE source_links (page_id TEXT PRIMARY KEY, manual_id TEXT, tiff_path TEXT, ocr_path TEXT, rescarta_url TEXT, source_url TEXT)"
    )
    conn.execute(
        "INSERT INTO source_links VALUES (?, ?, ?, ?, ?, ?)",
        (
            "t_p_120_1176_p000042",
            "t_p_120_1176",
            "local_data/rescarta_exports/t_p_120_1176/pages/000042_00000042.tif",
            "local_data/rescarta_exports/t_p_120_1176/ocr/000042_00000042.txt",
            "http://localhost:8080/rescarta/t_p_120_1176/000042",
            "http://localhost:8080/rescarta/t_p_120_1176/000042",
        ),
    )
    updated = update_source_link_urls(conn, DEFAULT_TEMPLATE, "https://rescarta.example.org/ResCarta-Web")
    assert updated == 1
    row = conn.execute("SELECT rescarta_url, source_url FROM source_links").fetchone()
    assert row["rescarta_url"].startswith("https://rescarta.example.org/ResCarta-Web")
    assert row["source_url"] == row["rescarta_url"]
