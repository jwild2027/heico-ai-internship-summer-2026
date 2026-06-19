from pathlib import Path

MODULE = Path("tiff/trace_net_table_line_geometry_v1.py")
text = MODULE.read_text(encoding="utf-8")

# 1) Create a morphology-only guard view after crop_guard_metadata is built.
crop_guard_block = """        crop_guard_metadata: Dict[str, Any] = {
            "crop_completeness_guard_available": bool(crop_guard_card),
            "crop_completeness_status": crop_guard_card.get("crop_completeness_status") if crop_guard_card else None,
            "crop_completeness_human_review_verdict": crop_guard_card.get("human_review_verdict") if crop_guard_card else None,
            "crop_completeness_guard_selection_allowed": crop_guard_card.get("crop_selection_allowed") if crop_guard_card else None,
            "crop_completeness_guard_selection_blocked": bool(crop_guard_card.get("crop_selection_blocked")) if crop_guard_card else False,
            "crop_completeness_guard_review_flags": list(crop_guard_card.get("review_flags") or []) if crop_guard_card else [],
            "crop_completeness_guard_recommended_actions": list(crop_guard_card.get("recommended_actions") or []) if crop_guard_card else [],
        }
"""

crop_guard_replacement = """        crop_guard_metadata: Dict[str, Any] = {
            "crop_completeness_guard_available": bool(crop_guard_card),
            "crop_completeness_status": crop_guard_card.get("crop_completeness_status") if crop_guard_card else None,
            "crop_completeness_human_review_verdict": crop_guard_card.get("human_review_verdict") if crop_guard_card else None,
            "crop_completeness_guard_selection_allowed": crop_guard_card.get("crop_selection_allowed") if crop_guard_card else None,
            "crop_completeness_guard_selection_blocked": bool(crop_guard_card.get("crop_selection_blocked")) if crop_guard_card else False,
            "crop_completeness_guard_review_flags": list(crop_guard_card.get("review_flags") or []) if crop_guard_card else [],
            "crop_completeness_guard_recommended_actions": list(crop_guard_card.get("recommended_actions") or []) if crop_guard_card else [],
        }
        morphology_crop_guard_metadata = dict(crop_guard_metadata)
        paddle_style_bbox_override_crop_guard = bool(
            paddle_style_bbox_metadata.get("table_paddle_style_bbox_selected_for_geometry")
            and not paddle_style_bbox_metadata.get("table_paddle_style_review_required")
            and not paddle_style_bbox_metadata.get("table_paddle_style_bbox_crop_rejected")
        )
        if paddle_style_bbox_override_crop_guard:
            # Paddle-style bbox resolver is now the stronger bbox validator.
            # Preserve legacy crop-completeness fields for audit, but allow
            # morphology selection to evaluate the selected Paddle-style crop.
            morphology_crop_guard_metadata["crop_completeness_guard_selection_allowed"] = True
            morphology_crop_guard_metadata["crop_completeness_guard_selection_blocked"] = False
            morphology_crop_guard_metadata["paddle_style_bbox_override_crop_guard_for_morphology"] = True
"""

if "paddle_style_bbox_override_crop_guard = bool(" not in text:
    if crop_guard_block not in text:
        raise SystemExit("Could not find crop_guard_metadata block; current file shape changed.")
    text = text.replace(crop_guard_block, crop_guard_replacement, 1)

# 2) Ensure the initial morphology comparison exposes the override bit.
old = """            **paddle_style_bbox_metadata,
            **crop_guard_metadata,
"""
new = """            **paddle_style_bbox_metadata,
            **crop_guard_metadata,
            "paddle_style_bbox_override_crop_guard_for_morphology": paddle_style_bbox_override_crop_guard,
"""
if old in text and '"paddle_style_bbox_override_crop_guard_for_morphology": paddle_style_bbox_override_crop_guard' not in text:
    text = text.replace(old, new, 1)

# 3) Pass the morphology guard view to choose_region_or_page_morphology.
old = """                bbox_resolver_metadata,
                crop_guard_metadata,
            )
"""
new = """                bbox_resolver_metadata,
                morphology_crop_guard_metadata,
            )
"""
if old not in text and "morphology_crop_guard_metadata,\n            )" not in text:
    raise SystemExit("Could not find choose_region_or_page_morphology guard argument block.")
if old in text:
    text = text.replace(old, new, 1)

# 4) Keep original guard fields on image_result, plus the override audit bit.
old = """            image_result.update(paddle_style_bbox_metadata)
            image_result.update(crop_guard_metadata)
"""
new = """            image_result.update(paddle_style_bbox_metadata)
            image_result.update(crop_guard_metadata)
            image_result["paddle_style_bbox_override_crop_guard_for_morphology"] = paddle_style_bbox_override_crop_guard
"""
if old in text and 'image_result["paddle_style_bbox_override_crop_guard_for_morphology"]' not in text:
    text = text.replace(old, new, 1)

# 5) Review blocking should follow the morphology decision guard view.
old = """        crop_guard_selection_allowed_for_card = crop_guard_metadata.get("crop_completeness_guard_selection_allowed") is True
        crop_blocked_by_guard_for_card = (
            not crop_guard_selection_allowed_for_card
            and bool(crop_selection_comparison.get("crop_selection_blocked_by_completeness_guard"))
        )
"""
new = """        crop_guard_selection_allowed_for_card = morphology_crop_guard_metadata.get("crop_completeness_guard_selection_allowed") is True
        crop_blocked_by_guard_for_card = (
            not crop_guard_selection_allowed_for_card
            and bool(crop_selection_comparison.get("crop_selection_blocked_by_completeness_guard"))
        )
"""
if old in text:
    text = text.replace(old, new, 1)

# 6) Output card should preserve legacy state and expose the override.
old = """            "crop_selection_blocked_by_completeness_guard": (
                crop_guard_metadata.get("crop_completeness_guard_selection_allowed") is not True
                and bool(crop_selection_comparison.get("crop_selection_blocked_by_completeness_guard"))
            ),
"""
new = """            "crop_selection_blocked_by_completeness_guard": (
                morphology_crop_guard_metadata.get("crop_completeness_guard_selection_allowed") is not True
                and bool(crop_selection_comparison.get("crop_selection_blocked_by_completeness_guard"))
            ),
            "legacy_crop_completeness_guard_selection_blocked": crop_guard_metadata.get("crop_completeness_guard_selection_blocked"),
            "paddle_style_bbox_override_crop_guard_for_morphology": paddle_style_bbox_override_crop_guard,
"""
if old in text and '"legacy_crop_completeness_guard_selection_blocked":' not in text:
    text = text.replace(old, new, 1)

# 7) Add summary counts.
old = """        "table_paddle_style_bbox_review_required_card_count": sum(1 for card in cards if card.get("table_paddle_style_review_required")),
        "page_morphology_selected_card_count": sum(1 for card in cards if card.get("selected_morphology_scope") == "page"),
"""
new = """        "table_paddle_style_bbox_review_required_card_count": sum(1 for card in cards if card.get("table_paddle_style_review_required")),
        "paddle_style_bbox_override_crop_guard_for_morphology_count": sum(1 for card in cards if card.get("paddle_style_bbox_override_crop_guard_for_morphology")),
        "legacy_crop_completeness_guard_selection_blocked_count": sum(1 for card in cards if card.get("legacy_crop_completeness_guard_selection_blocked")),
        "page_morphology_selected_card_count": sum(1 for card in cards if card.get("selected_morphology_scope") == "page"),
"""
if old in text and "paddle_style_bbox_override_crop_guard_for_morphology_count" not in text:
    text = text.replace(old, new, 1)

# 8) Print new summary fields from CLI.
old = """        "table_paddle_style_bbox_review_required_card_count",
        "page_morphology_selected_card_count",
"""
new = """        "table_paddle_style_bbox_review_required_card_count",
        "paddle_style_bbox_override_crop_guard_for_morphology_count",
        "legacy_crop_completeness_guard_selection_blocked_count",
        "page_morphology_selected_card_count",
"""
if old in text and '"paddle_style_bbox_override_crop_guard_for_morphology_count",' not in text:
    text = text.replace(old, new, 1)

MODULE.write_text(text, encoding="utf-8")
print("patched table_line_geometry Paddle-style bbox morphology override")
