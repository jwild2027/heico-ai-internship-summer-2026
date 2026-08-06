import json
from pathlib import Path

from tiff.trace_net_image_visual_summary_v1 import _ocr_text_lookup


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_ocr_text_lookup_reads_fishnet_page_features_and_cell_records(tmp_path: Path) -> None:
    fishnet_path = _write_json(
        tmp_path / "fishnet.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "source_p000005",
                    "page_number": 5,
                    "page_ocr_features": {
                        "sample_text": "Passenger Seats Component Maintenance Manual",
                    },
                    "cell_records": [
                        {"sample_text": "CHAPTER SECTION", "ocr_status": "ok"},
                        {"sample_text": "Illustrated Parts List", "ocr_status": "ok"},
                    ],
                }
            ],
        },
    )

    lookup = _ocr_text_lookup(fishnet_path)

    assert 5 in lookup
    assert "Passenger Seats" in lookup[5]
    assert "CHAPTER SECTION" in lookup[5]
    assert "Illustrated Parts List" in lookup[5]


def test_ocr_text_lookup_reads_nested_word_boxes_without_top_level_text(tmp_path: Path) -> None:
    fishnet_path = _write_json(
        tmp_path / "fishnet.json",
        {
            "records": [
                {
                    "page_id": "t_p_120_1176_p000017",
                    "cell_records": [
                        {
                            "ocr_word_boxes": [
                                {"text": "SEAT"},
                                {"word": "DIMENSIONS"},
                            ]
                        }
                    ],
                }
            ]
        },
    )

    lookup = _ocr_text_lookup(fishnet_path)

    assert 17 in lookup
    assert "SEAT" in lookup[17]
    assert "DIMENSIONS" in lookup[17]
