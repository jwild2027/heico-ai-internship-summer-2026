from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from tiff.visual_text_extraction import (
    ExtractionOptions,
    VisualTextPaths,
    default_visual_text_safety_layers,
    parse_visual_text_safety_layers,
    run_visual_text_extraction,
)


class LayerAwareClient:
    provider_name = "mock"
    model_name = "layer-aware-vision"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def describe_page(self, image_path: Path, prompt: str, metadata: Mapping[str, Any]) -> str:
        call = dict(metadata)
        self.calls.append(call)
        if int(call.get("fishnet_layer_index") or 0) == 0:
            raise RuntimeError("simulated primary timeout")
        return """# Page visual text

## Page type
parts_list

## Visible title/header
Mock rescue page

## Transcribed visible text
Visible rescued text with part ABC-123-001.

## Visual summary
The rescue layer produced usable visual text.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
No readable figure or diagram detected.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
- ABC-123-001

## Warnings/notes
No visible warnings, cautions, notes, revision notes, or procedural notes detected.

## Uncertain/unreadable
No uncertain or unreadable visual regions reported.

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""


def _write_page_cards(tmp_path: Path) -> VisualTextPaths:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"not really an image; fake client does not decode")
    page_cards = tmp_path / "page_cards.json"
    page_cards.write_text(
        json.dumps(
            {
                "page_character_cards": [
                    {
                        "page_id": "test_page_001",
                        "entity_id": "page:test_page_001",
                        "page_role": "parts_list",
                        "image_classification": "likely_table_or_grid",
                        "parents": {"document_label": "manual", "ata_code": "25-21-00"},
                        "source": {"tiff_path": str(image_path), "source_url": "local://test"},
                        "context": {"summary": "test page"},
                        "parts": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return VisualTextPaths(page_cards_path=page_cards, page_index_path=tmp_path / "missing.json", output_dir=tmp_path / "visual_text")


def test_parse_default_fishnet_layers() -> None:
    layers = default_visual_text_safety_layers()
    assert [layer.name for layer in layers] == ["rescue_768", "rescue_512"]
    assert layers[0].max_image_edge == 768
    assert layers[0].timeout_seconds == 1200


def test_parse_custom_safety_layer_spec() -> None:
    layers = parse_visual_text_safety_layers("small:768:1200:0.1:2500:noocr,tiny:512:900")
    assert len(layers) == 2
    assert layers[0].name == "small"
    assert layers[0].max_image_edge == 768
    assert layers[0].timeout_seconds == 1200
    assert layers[0].temperature == 0.1
    assert layers[0].ocr_max_chars == 2500
    assert layers[0].ocr_assist is False
    assert layers[1].name == "tiny"
    assert layers[1].max_image_edge == 512


def test_fishnet_rescues_page_after_primary_failure(tmp_path: Path) -> None:
    paths = _write_page_cards(tmp_path)
    client = LayerAwareClient()
    options = ExtractionOptions(
        provider="mock",
        model="mock",
        max_pages=1,
        overwrite=True,
        max_image_edge=1024,
        timeout_seconds=600,
        prompt_version="visual_text_v2_2",
        safety_layers=parse_visual_text_safety_layers("rescue_768:768:1200"),
        progress=False,
    )

    result = run_visual_text_extraction(paths, options, client=client)

    assert result.status == "OK"
    assert len(client.calls) == 2
    assert client.calls[0]["fishnet_layer"] == "primary"
    assert client.calls[0]["max_image_edge"] == 1024
    assert client.calls[1]["fishnet_layer"] == "rescue_768"
    assert client.calls[1]["max_image_edge"] == 768

    record = result.records[0]
    assert record["status"] == "ok"
    assert record["fishnet_rescued"] is True
    assert record["fishnet_layer"] == "rescue_768"
    assert len(record["fishnet_attempts"]) == 2
    assert record["fishnet_attempts"][0]["status"] == "error"
    assert record["fishnet_attempts"][1]["status"] == "ok"

    summary = result.summary
    assert summary["fishnet_safety_layers_enabled"] is True
    assert summary["fishnet_rescued_records"] == 1
    assert summary["fishnet_failed_records"] == 0
    assert summary["fishnet_attempt_total"] == 2
    assert summary["fishnet_layer_counts"]["rescue_768"] == 1
