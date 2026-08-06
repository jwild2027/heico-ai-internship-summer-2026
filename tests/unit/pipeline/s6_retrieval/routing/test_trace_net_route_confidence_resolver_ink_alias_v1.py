"""Patch 1 reproduction — the resolver silently loses the scan-pack ink field.

The OCR route scan pack emits ``ink_ratio_estimate`` (spread at the top level of
each page record via ``**features``), but the route-confidence resolver's
``_ink_density`` only read ``ink_density`` / ``dark_pixel_ratio`` /
``foreground_ratio``. Valid ink therefore collapsed to ``0.0``.

These tests pin the small, explicit, deterministic ink-field contract:
canonical aliases (ink_ratio_estimate, ink_ratio, ink_density, dark_pixel_ratio,
foreground_ratio) read at the top level and inside the canonical nested feature
containers (image_features, page_ink_features, ink_features), with invalid/absent
values falling through to 0.0 and never masking a valid alias.
"""
from tiff.trace_net_route_confidence_resolver_v1 import _ink_density


def test_top_level_ink_ratio_estimate_is_read():
    # The exact shape the scan pack produces (features spread top-level).
    assert _ink_density({"ink_ratio_estimate": 0.053}) == 0.053


def test_top_level_ink_ratio_alias_is_read():
    # The name used in the 509 audit CSV.
    assert _ink_density({"ink_ratio": 0.041}) == 0.041


def test_nested_image_features_ink_ratio_estimate_is_read():
    assert _ink_density({"image_features": {"ink_ratio_estimate": 0.07}}) == 0.07


def test_nested_page_ink_features_alias_is_read():
    assert _ink_density({"page_ink_features": {"ink_ratio": 0.02}}) == 0.02


def test_existing_ink_density_behavior_is_unchanged():
    assert _ink_density({"ink_density": 0.08}) == 0.08
    assert _ink_density({"dark_pixel_ratio": 0.09}) == 0.09
    assert _ink_density({"foreground_ratio": 0.11}) == 0.11


def test_invalid_string_falls_through_safely():
    assert _ink_density({"ink_ratio_estimate": "n/a"}) == 0.0


def test_missing_value_returns_zero():
    assert _ink_density({}) == 0.0


def test_does_not_choose_zero_when_a_valid_alias_exists():
    # A present-but-None canonical key must not shadow a valid alias.
    assert _ink_density({"ink_density": None, "ink_ratio_estimate": 0.05}) == 0.05


def test_real_scan_pack_record_shape_is_read():
    # Mirrors trace_net_ocr_route_scan_pack_v1 record: features spread top-level.
    record = {
        "page_id": "t_p_120_1176_p000001",
        "accepted_route": "table",
        "ocr_sample_text": "PART NUMBER ASSY",
        "image_feature_status": "ok",
        "ink_ratio_estimate": 0.052971,
        "mean_darkness_estimate": 0.03,
    }
    assert _ink_density(record) == 0.052971


def test_genuine_zero_is_preserved():
    # A blank page legitimately reports 0.0 ink; that value is returned, not masked.
    assert _ink_density({"ink_ratio_estimate": 0.0}) == 0.0
