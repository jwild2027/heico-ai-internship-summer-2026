import json
from pathlib import Path

import pytest

from tiff.trace_net_route_dispatch_contract_loader_v1 import (
    ROUTE_BLANK_CANDIDATE,
    ROUTE_IMAGE_VISUAL,
    ROUTE_NORMAL_TEXT,
    ROUTE_REVIEW,
    ROUTE_TABLE,
    RouteDispatchProcessorContract,
    is_page_allowed_for_route,
    load_route_dispatch_processor_contract,
    page_aliases,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sample_contract() -> dict:
    return {
        "schema_version": "trace_net_route_dispatch_processor_contract_v1",
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "processor_contract_card_count": 3,
            "table_processor_allowed_page_count": 1,
            "image_visual_processor_allowed_page_count": 2,
            "normal_text_processor_allowed_page_count": 1,
            "blank_candidate_processor_allowed_page_count": 1,
            "review_required_page_count": 1,
            "unsafe_contract_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "processor_contract_cards": [
            {
                "page_id": "t_p_120_1176_p000005",
                "source_page_id": "metadata_page_000005",
                "page_number": 5,
                "table_processing_allowed": True,
                "image_visual_processing_allowed": True,
                "normal_text_processing_allowed": False,
                "blank_candidate_processing_allowed": False,
                "review_processing_required": False,
                "safe_for_routing": True,
            },
            {
                "page_id": "t_p_120_1176_p000012",
                "source_page_id": "metadata_page_000012",
                "page_number": 12,
                "table_processing_allowed": False,
                "image_visual_processing_allowed": True,
                "normal_text_processing_allowed": True,
                "blank_candidate_processing_allowed": False,
                "review_processing_required": True,
                "safe_for_routing": True,
            },
            {
                "page_id": "t_p_120_1176_p000035",
                "source_page_id": "metadata_page_000035",
                "page_number": 35,
                "table_processing_allowed": False,
                "image_visual_processing_allowed": False,
                "normal_text_processing_allowed": False,
                "blank_candidate_processing_allowed": True,
                "review_processing_required": False,
                "safe_for_routing": True,
            },
        ],
    }


def test_page_aliases_include_trace_net_and_metadata_ids() -> None:
    aliases = page_aliases(page_id="t_p_120_1176_p000005", source_page_id="metadata_page_000005", page_number=5)
    assert "t_p_120_1176_p000005" in aliases
    assert "metadata_page_000005" in aliases
    assert "5" in aliases


def test_loader_resolves_page_id_source_page_id_and_page_number(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    _write_json(path, _sample_contract())
    contract = load_route_dispatch_processor_contract(path)

    assert contract.is_table_allowed("t_p_120_1176_p000005") is True
    assert contract.is_table_allowed("metadata_page_000005") is True
    assert contract.is_table_allowed(5) is True
    assert contract.is_image_visual_allowed(page_number=5) is True
    assert contract.is_normal_text_allowed("t_p_120_1176_p000005") is False


def test_loader_returns_allowed_routes_and_review_required() -> None:
    contract = RouteDispatchProcessorContract.from_payload(_sample_contract())

    assert contract.allowed_routes("metadata_page_000012") == [ROUTE_IMAGE_VISUAL, ROUTE_NORMAL_TEXT, ROUTE_REVIEW]
    assert contract.is_review_required("metadata_page_000012") is True
    assert contract.is_blank_candidate("metadata_page_000035") is True
    assert contract.allowed_routes("metadata_page_000035") == [ROUTE_BLANK_CANDIDATE]


def test_loader_rejects_unknown_route() -> None:
    contract = RouteDispatchProcessorContract.from_payload(_sample_contract())
    with pytest.raises(ValueError):
        contract.is_allowed("metadata_page_000005", "bad_route")


def test_loader_blocks_unsafe_contract_card() -> None:
    payload = _sample_contract()
    payload["processor_contract_cards"][0]["safe_for_routing"] = False
    contract = RouteDispatchProcessorContract.from_payload(payload)

    assert contract.is_table_allowed("metadata_page_000005") is False
    assert contract.allowed_routes("metadata_page_000005") == []


def test_page_ids_for_route_and_summary() -> None:
    contract = RouteDispatchProcessorContract.from_payload(_sample_contract())

    assert contract.table_page_ids() == ["t_p_120_1176_p000005"]
    assert contract.image_visual_page_ids() == ["t_p_120_1176_p000005", "t_p_120_1176_p000012"]
    summary = contract.guard_summary()
    assert summary["table_page_count"] == 1
    assert summary["image_visual_page_count"] == 2
    assert summary["answer_permission"] is False
    assert summary["source_truth_mutation_allowed"] is False


def test_module_level_route_check(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    _write_json(path, _sample_contract())
    assert is_page_allowed_for_route(path, "metadata_page_000005", ROUTE_TABLE) is True
    assert is_page_allowed_for_route(path, "metadata_page_000035", ROUTE_TABLE) is False
