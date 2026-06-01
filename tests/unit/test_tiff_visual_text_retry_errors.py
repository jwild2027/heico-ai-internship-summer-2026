from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from tiff.visual_text_extraction import (
    ExtractionOptions,
    MockVisualTextClient,
    VisualTextPaths,
    run_visual_text_extraction,
)
from tiff.visual_text_extraction_quality import (
    build_visual_text_extraction_quality,
    VisualTextQualityPaths,
)


class FailsOnePageClient:
    provider_name = "mock"
    model_name = "flaky-mock"

    def describe_page(self, image_path: Path, prompt: str, metadata: Mapping[str, Any]) -> str:
        if metadata.get("page_id") == "p002":
            raise TimeoutError("mock timeout")
        return "# Page visual text\n\n## Visual summary\nReadable mock output for p001."


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_fixture(tmp_path: Path) -> VisualTextPaths:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"mock image")
    cards_path = tmp_path / "page_character_cards.json"
    page_index_path = tmp_path / "page_index.json"
    output_dir = tmp_path / "visual_text"
    _write_json(
        cards_path,
        {
            "page_cards": [
                {
                    "page_id": "p001",
                    "context": {"page_role": "figure"},
                    "signals": {"image_classification": "likely_figure_or_diagram"},
                    "source": {"tiff_path": str(image_path)},
                },
                {
                    "page_id": "p002",
                    "context": {"page_role": "table"},
                    "signals": {"image_classification": "likely_table_or_grid"},
                    "source": {"tiff_path": str(image_path)},
                },
            ]
        },
    )
    _write_json(page_index_path, {"pages": []})
    return VisualTextPaths(page_cards_path=cards_path, page_index_path=page_index_path, output_dir=output_dir)


def test_retry_errors_only_preserves_successes_and_reprocesses_failed_pages(tmp_path: Path) -> None:
    paths = _make_fixture(tmp_path)

    first = run_visual_text_extraction(
        paths,
        ExtractionOptions(provider="mock", max_pages=2, overwrite=True),
        client=FailsOnePageClient(),
    )

    assert first.status == "PARTIAL"
    assert first.summary["ok_records"] == 1
    assert first.summary["error_records"] == 1

    second = run_visual_text_extraction(
        paths,
        ExtractionOptions(
            provider="mock",
            max_pages=2,
            overwrite=False,
            retry_error_pages_only=True,
        ),
        client=MockVisualTextClient(),
    )

    assert second.status == "OK"
    assert second.summary["retry_error_pages_only"] is True
    assert second.summary["ok_records"] == 2
    assert second.summary["error_records"] == 0
    assert sorted(record["page_id"] for record in second.records) == ["p001", "p002"]


def test_quality_can_optionally_accept_partial_runs_with_allowed_error_count(tmp_path: Path) -> None:
    paths = _make_fixture(tmp_path)
    run_visual_text_extraction(
        paths,
        ExtractionOptions(provider="mock", max_pages=2, overwrite=True),
        client=FailsOnePageClient(),
    )

    strict = build_visual_text_extraction_quality(
        VisualTextQualityPaths(output_dir=paths.output_dir),
        allow_planned=False,
        max_error_records=1,
    )
    tolerant = build_visual_text_extraction_quality(
        VisualTextQualityPaths(output_dir=paths.output_dir),
        allow_planned=False,
        max_error_records=1,
        allow_partial_status=True,
    )

    assert strict["status"] == "FAIL"
    assert tolerant["status"] == "OK"
    assert tolerant["summary"]["visual_text_error_records"] == 1
