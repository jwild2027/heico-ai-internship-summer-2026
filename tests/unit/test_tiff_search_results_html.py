from pathlib import Path

from tiff.search_index import SearchResult
from tiff.search_results_html import path_to_file_uri, render_search_results_html, write_search_results_html


def make_result() -> SearchResult:
    return SearchResult(
        page_id="manual_p000001",
        manual_id="manual",
        publication_number="T.P. 120/1176",
        ata_code="25-21-00",
        page_sequence=1,
        page_label="1001",
        page_type="maintenance_manual_ipl",
        title="CONTENTS",
        tiff_path="local_data/rescarta_exports/manual/pages/000001.tif",
        ocr_text_path="local_data/rescarta_exports/manual/ocr/000001.txt",
        thumbnail_path=None,
        rescarta_object_id="manual",
        rescarta_page_id="000001",
        matched_part_number=None,
        matched_part_number_normalized=None,
        match_source="keyword-and",
        snippet="This is a result snippet",
        rank=0.0,
    )


def test_path_to_file_uri_resolves_relative_path(tmp_path: Path) -> None:
    uri = path_to_file_uri("local_data/example.tif", base_dir=tmp_path)
    assert uri is not None
    assert uri.startswith("file:")
    assert "local_data" in uri
    assert "example.tif" in uri


def test_render_search_results_html_contains_clickable_links(tmp_path: Path) -> None:
    html = render_search_results_html(
        query="T.P. 120/1176",
        results=[make_result()],
        db_path="local_data/db/tiff_search.db",
        base_dir=tmp_path,
    )
    assert "Local TIFF" in html or "TIFF Search Results" in html
    assert "T.P. 120/1176" in html
    assert "Open TIFF" in html
    assert "Open OCR text" in html
    assert "file:" in html
    assert "result-1" in html


def test_write_search_results_html_creates_file(tmp_path: Path) -> None:
    output = tmp_path / "results" / "search.html"
    written = write_search_results_html(
        query="120-50648-533",
        results=[make_result()],
        output_path=output,
        base_dir=tmp_path,
    )
    assert written == output
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "120-50648-533" in text
    assert "Open TIFF" in text
