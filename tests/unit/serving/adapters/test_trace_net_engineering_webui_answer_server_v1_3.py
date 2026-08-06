
from tiff.trace_net_engineering_webui_answer_server_v1 import LLMConfig
from tiff.trace_net_engineering_webui_answer_server_v1_3 import (
    build_clean_search_fallback,
    answer_question_v13,
)


def test_clean_fallback_has_no_debug_tokens():
    hits = [
        {
            "page_id": "source_p000485",
            "page_number": 485,
            "route": "unknown",
            "text": "trace_net_fishnet_ocr_grid_v1 router_classifier_input_only Typical Repair to Passenger Seat Leg 120-29073-005 repair doubler original fastener",
            "has_text": True,
        }
    ]
    text = build_clean_search_fallback(
        question="find repair information for passenger seat legs",
        hits=hits,
        citations=[],
    )
    assert "router_classifier_input_only" not in text
    assert "fishnet_page_grid_card" not in text
    assert "source_p000485" in text
    assert "repair doubler" in text.lower()


def test_v13_nonmatching_part_uses_search():
    pages = [
        {
            "page_id": "source_p000243",
            "page_number": 243,
            "route": "table",
            "text": "120-45851-003 DOUBLE PASSENGER SEAT ASSY",
            "has_text": True,
        }
    ]
    gated = [
        {
            "user_question": "Find part number 120-29073-001 and nearby similar parts.",
            "seed_part_numbers": ["120-29073-001"],
            "draft_text": "wrong cached draft",
        }
    ]
    answer = answer_question_v13(
        question="find part number 120-45851-003",
        pages=pages,
        gated_drafts=gated,
        llm_config=LLMConfig(mode="off"),
    )
    assert answer["intent"] == "fallback_search"
    assert "120-45851-003" in answer["response_text"]
    assert "wrong cached draft" not in answer["response_text"]
    assert "Source notes:" in answer["response_text"]
