from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from tiff.source_links import (
    build_source_links,
    enrich_sources_with_source_links,
    summarize_source_links,
    write_source_link_report,
)


@dataclass(frozen=True)
class FakeSource:
    page_id: str
    rescarta_object_id: str | None = None
    rescarta_page_id: str | None = None
    extra: dict = field(default_factory=dict)


def make_pages_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE pages (
                page_id TEXT PRIMARY KEY,
                manual_id TEXT,
                publication_number TEXT,
                ata_code TEXT,
                page_sequence INTEGER,
                page_label TEXT,
                page_type TEXT,
                title TEXT,
                tiff_path TEXT,
                ocr_text_path TEXT,
                thumbnail_path TEXT,
                rescarta_object_id TEXT,
                rescarta_page_id TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO pages VALUES (
                't_p_120_1176_p000083', 't_p_120_1176', 'T.P. 120/1176',
                '25-21-00', 83, '1056', 'maintenance_manual_ipl', 'IPL',
                'local_data/rescarta_exports/t_p_120_1176/pages/000083_00000083.tif',
                'local_data/rescarta_exports/t_p_120_1176/ocr/000083_00000083.txt',
                NULL, 't_p_120_1176', '000083'
            )
            """
        )
        conn.commit()


def test_build_source_links_from_pages(tmp_path):
    db_path = tmp_path / "search.db"
    make_pages_db(db_path)

    summary = build_source_links(
        db_path,
        rescarta_url_template="http://localhost/rescarta/{object_id}/{page_id}",
    )

    assert summary.pages_seen == 1
    assert summary.links_written == 1
    assert summary.rescarta_urls_written == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT page_id, rescarta_url, source_url FROM source_links").fetchone()
    assert row[0] == "t_p_120_1176_p000083"
    assert row[1] == "http://localhost/rescarta/t_p_120_1176/000083"
    assert row[2] == "http://localhost/rescarta/t_p_120_1176/000083"


def test_enrich_sources_with_source_links(tmp_path):
    db_path = tmp_path / "search.db"
    make_pages_db(db_path)
    build_source_links(db_path, rescarta_url_template="http://localhost/rescarta/{object_id}/{page_id}")

    source = FakeSource(page_id="t_p_120_1176_p000083")
    enriched = enrich_sources_with_source_links(db_path, (source,))[0]

    assert enriched.rescarta_object_id == "t_p_120_1176"
    assert enriched.rescarta_page_id == "000083"
    assert enriched.extra["rescarta_url"] == "http://localhost/rescarta/t_p_120_1176/000083"
    assert enriched.extra["source_link_id"].startswith("t_p_120_1176:")


def test_write_source_link_report(tmp_path):
    db_path = tmp_path / "search.db"
    make_pages_db(db_path)
    build_source_links(db_path)

    report = write_source_link_report(db_path, output_dir=tmp_path / "reports")

    assert report.total_links == 1
    assert report.output_csv and report.output_csv.exists()
    assert report.output_json and report.output_json.exists()
    assert report.output_html and report.output_html.exists()
    summary = summarize_source_links(db_path)
    assert summary.total_links == 1
