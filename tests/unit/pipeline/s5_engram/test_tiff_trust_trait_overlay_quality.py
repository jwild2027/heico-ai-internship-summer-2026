import json
from pathlib import Path

from tiff.trust_trait_overlay import TrustTraitOverlayPaths, build_trust_trait_quality, export_trust_trait_overlay


def _record(page_id: str, tier: str):
    return {
        "page_id": page_id,
        "status": "ok",
        "visual_text_cleanup_scores": {
            "trust_tier": tier,
            "usable_for_rag": tier in {"A", "B"},
            "requires_human_review": tier in {"C", "D"},
        },
        "visual_text_scores_clean": {
            "required_sections_present": True,
            "metadata_leakage_risk": False,
            "refusal_like": False,
        },
    }


def _write_records(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def test_trust_trait_quality_passes_for_exported_overlay(tmp_path: Path):
    records_path = tmp_path / "visual_text" / "visual_text_extraction_clean.jsonl"
    _write_records(records_path, [_record("p001", "A"), _record("p002", "C")])
    paths = TrustTraitOverlayPaths(output_dir=tmp_path / "trust", clean_records_path=records_path)
    export_trust_trait_overlay(paths)

    report = build_trust_trait_quality(paths, min_records=2, expect_pages=2)

    assert report["status"] == "OK"
    assert report["summary"]["trust_trait_records"] == 2
    assert report["summary"]["trust_trait_pages"] == 2
    assert report["summary"]["trust_trait_tier_A"] == 1
    assert report["summary"]["trust_trait_tier_C"] == 1


def test_trust_trait_quality_can_fail_on_d_tier_limit(tmp_path: Path):
    records_path = tmp_path / "visual_text" / "visual_text_extraction_clean.jsonl"
    _write_records(records_path, [_record("p001", "D")])
    paths = TrustTraitOverlayPaths(output_dir=tmp_path / "trust", clean_records_path=records_path)
    export_trust_trait_overlay(paths)

    report = build_trust_trait_quality(paths, min_records=1, expect_pages=1, max_trust_d_records=0)

    assert report["status"] == "FAIL"
    assert any(check["name"] == "trust_trait_trust_d" and not check["ok"] for check in report["checks"])
