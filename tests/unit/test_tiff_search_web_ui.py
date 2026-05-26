from pathlib import Path

from tiff.search_index import SearchResult
from tiff.search_web_ui import (
    SearchRequest,
    clamp_limit,
    csv_text_for_results,
    parse_search_request,
    render_page,
    resolve_source_path,
)


def sample_result() -> SearchResult:
    return SearchResult(
        page_id="manual_p000001",
        manual_id="manual",
        publication_number="T.P. 120/1176",
        ata_code="25-21-00",
        page_sequence=1,
        page_label="1001",
        page_type="maintenance_manual_ipl",
        title="TEST PAGE",
        tiff_path="local_data\\rescarta_exports\\manual\\pages\\000001.tif",
        ocr_text_path="local_data/rescarta_exports/manual/ocr/000001.txt",
        thumbnail_path=None,
        rescarta_object_id="manual",
        rescarta_page_id="000001",
        matched_part_number="120-37313-001",
        matched_part_number_normalized="12037313001",
        match_source="part-number",
        snippet="ITEM PART NO 120-37313-001 BRACKET ASSY",
        rank=0.0,
    )


def test_parse_search_request_and_limit_clamping():
    req = parse_search_request({"q": [" 120-37313-001 "], "mode": ["part"], "limit": ["9999"]})
    assert req.query == "120-37313-001"
    assert req.mode == "part"
    assert req.limit == 200
    assert clamp_limit("bad") == 25
    assert clamp_limit("0") == 1


def test_render_page_contains_search_result_and_buttons(tmp_path: Path):
    db_path = tmp_path / "tiff_search.db"
    html = render_page(
        SearchRequest(query="120-37313-001", mode="part", limit=10),
        [sample_result()],
        db_path=db_path,
    )
    assert "Local TIFF Search" in html
    assert "120-37313-001" in html
    assert "View TIFF in browser" in html
    assert "Export CSV" in html


def test_csv_text_for_results_has_expected_columns():
    csv_text = csv_text_for_results([sample_result()])
    assert "match_source,matched_part_number" in csv_text
    assert "part-number,120-37313-001" in csv_text
    assert "local_data" in csv_text


def test_resolve_source_path_handles_relative_windows_style_path(tmp_path: Path):
    file_path = tmp_path / "local_data" / "rescarta_exports" / "manual" / "pages" / "000001.tif"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"fake")
    resolved = resolve_source_path(
        "local_data\\rescarta_exports\\manual\\pages\\000001.tif",
        repo_root=tmp_path,
    )
    assert resolved == file_path.resolve()
