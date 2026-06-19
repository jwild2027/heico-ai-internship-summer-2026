from pathlib import Path

MODULE = Path("tiff/trace_net_table_line_geometry_v1.py")
text = MODULE.read_text(encoding="utf-8")

# 1) Add card-level extraction bbox fields after Paddle-style review fields.
marker = """            "table_paddle_style_review_required": paddle_style_bbox_metadata.get("table_paddle_style_review_required"),
            "table_paddle_style_review_reasons": paddle_style_bbox_metadata.get("table_paddle_style_review_reasons"),
            "table_image_resolver_available": bool(resolver_card),
"""

replacement = """            "table_paddle_style_review_required": paddle_style_bbox_metadata.get("table_paddle_style_review_required"),
            "table_paddle_style_review_reasons": paddle_style_bbox_metadata.get("table_paddle_style_review_reasons"),
            "table_paddle_style_bbox_selected_for_extraction": bool(
                paddle_style_bbox_metadata.get("table_paddle_style_bbox_selected_for_geometry")
                and not paddle_style_bbox_metadata.get("table_paddle_style_bbox_crop_rejected")
                and not paddle_style_bbox_metadata.get("table_paddle_style_review_required")
            ),
            "table_extraction_bbox_source": (
                "table_paddle_style_bbox_resolver"
                if paddle_style_bbox_metadata.get("table_paddle_style_bbox_selected_for_geometry")
                and not paddle_style_bbox_metadata.get("table_paddle_style_bbox_crop_rejected")
                and not paddle_style_bbox_metadata.get("table_paddle_style_review_required")
                else table_region_bbox_source
            ),
            "table_extraction_bbox": (
                paddle_style_bbox_metadata.get("table_paddle_style_selected_bbox")
                if paddle_style_bbox_metadata.get("table_paddle_style_bbox_selected_for_geometry")
                and not paddle_style_bbox_metadata.get("table_paddle_style_bbox_crop_rejected")
                and not paddle_style_bbox_metadata.get("table_paddle_style_review_required")
                else table_region_bbox
            ),
            "table_extraction_scope": (
                "paddle_style_bbox_crop"
                if paddle_style_bbox_metadata.get("table_paddle_style_bbox_selected_for_geometry")
                and not paddle_style_bbox_metadata.get("table_paddle_style_bbox_crop_rejected")
                and not paddle_style_bbox_metadata.get("table_paddle_style_review_required")
                else image_result.get("selected_morphology_scope")
            ),
            "table_image_resolver_available": bool(resolver_card),
"""

if "table_paddle_style_bbox_selected_for_extraction" not in text:
    if marker not in text:
        raise SystemExit("Could not find Paddle-style card field marker; current file shape changed.")
    text = text.replace(marker, replacement, 1)

# 2) Add summary counts near existing Paddle-style bbox summary fields.
summary_marker = """        "table_paddle_style_bbox_review_required_card_count": sum(1 for card in cards if card.get("table_paddle_style_review_required")),
        "paddle_style_bbox_override_crop_guard_for_morphology_count": sum(1 for card in cards if card.get("paddle_style_bbox_override_crop_guard_for_morphology")),
"""

summary_replacement = """        "table_paddle_style_bbox_review_required_card_count": sum(1 for card in cards if card.get("table_paddle_style_review_required")),
        "table_paddle_style_bbox_selected_for_extraction_count": sum(1 for card in cards if card.get("table_paddle_style_bbox_selected_for_extraction")),
        "table_extraction_bbox_paddle_style_count": sum(1 for card in cards if card.get("table_extraction_bbox_source") == "table_paddle_style_bbox_resolver"),
        "paddle_style_bbox_override_crop_guard_for_morphology_count": sum(1 for card in cards if card.get("paddle_style_bbox_override_crop_guard_for_morphology")),
"""

if "table_paddle_style_bbox_selected_for_extraction_count" not in text:
    if summary_marker not in text:
        raise SystemExit("Could not find Paddle-style summary marker; current file shape changed.")
    text = text.replace(summary_marker, summary_replacement, 1)

# 3) Print new summary fields from CLI.
print_marker = """        "table_paddle_style_bbox_review_required_card_count",
        "paddle_style_bbox_override_crop_guard_for_morphology_count",
"""

print_replacement = """        "table_paddle_style_bbox_review_required_card_count",
        "table_paddle_style_bbox_selected_for_extraction_count",
        "table_extraction_bbox_paddle_style_count",
        "paddle_style_bbox_override_crop_guard_for_morphology_count",
"""

if '"table_paddle_style_bbox_selected_for_extraction_count",' not in text:
    if print_marker not in text:
        raise SystemExit("Could not find Paddle-style CLI print marker; current file shape changed.")
    text = text.replace(print_marker, print_replacement, 1)

MODULE.write_text(text, encoding="utf-8")
print("patched table_line_geometry to expose Paddle-style extraction bbox")
