from tiff.trace_net_leiden_category_summary_hydrator_v1 import build_hydrator_report, check_quality, QualityThresholds


def sample_inputs():
    leiden = {
        "quality_status": "PASS",
        "communities": [
            {
                "community_id": "tracenet_community_00001",
                "label": "Part family community 120-29066",
                "page_ids": ["t_p_120_1176_p000001", "t_p_120_1176_p000002"],
                "part_numbers": ["120-29066-019"],
            },
            {"community_id": "tracenet_community_00224", "label": "TRACE-Net graph community", "page_ids": []},
        ],
    }
    category_overlay = {
        "quality_status": "PASS",
        "page_category_profiles": [
            {"page_id": "t_p_120_1176_p000001", "page_category_label": "text_source_page"},
            {"page_id": "t_p_120_1176_p000002", "category_counts": {"part": 3, "table": 1}},
        ],
    }
    taxonomy = {
        "quality_status": "PASS",
        "page_profiles": [
            {"page_id": "t_p_120_1176_p000001", "family_counts": {"source": 2}},
            {"page_id": "t_p_120_1176_p000002", "categories": ["part_candidate", "citation"]},
        ],
    }
    dc = {
        "quality_status": "PASS",
        "page_records": [
            {"page_id": "t_p_120_1176_p000001", "dc": {"dc:type": ["technical_manual_page", "text_page"]}},
            {"page_id": "t_p_120_1176_p000002", "dc": {"dc:type": ["technical_manual_page"]}},
        ],
    }
    graph_ui = {"quality_status": "PASS", "community_cards": []}
    audit = {"quality_status": "PASS", "community_audit_records": []}
    return leiden, category_overlay, taxonomy, dc, graph_ui, audit


def test_build_hydrates_category_summary_from_page_profiles():
    leiden, category_overlay, taxonomy, dc, graph_ui, audit = sample_inputs()
    report = build_hydrator_report(
        leiden_communities=leiden,
        category_aware_leiden_overlay=category_overlay,
        element_category_taxonomy=taxonomy,
        dublin_core_refined=dc,
        graph_ui_community_overlay=graph_ui,
        leiden_quality_audit=audit,
    )
    summary = report["summary"]
    records = report["community_hydration_records"]

    assert report["status"] == "LEIDEN_CATEGORY_SUMMARY_HYDRATED"
    assert summary["community_hydration_record_count"] == 2
    assert summary["category_summary_hydrated_count"] == 1
    assert summary["missing_page_membership_count"] == 1
    assert summary["community_as_proof_count"] == 0
    assert summary["category_as_proof_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0

    hydrated = next(r for r in records if r["community_id"] == "tracenet_community_00001")
    assert hydrated["category_summary_hydrated"] is True
    assert hydrated["can_answer_directly"] is False
    assert hydrated["can_prove_claims"] is False
    assert hydrated["retrieval_only"] is True
    assert hydrated["category_counts"]


def test_quality_passes_when_thresholds_met():
    leiden, category_overlay, taxonomy, dc, graph_ui, audit = sample_inputs()
    report = build_hydrator_report(
        leiden_communities=leiden,
        category_aware_leiden_overlay=category_overlay,
        element_category_taxonomy=taxonomy,
        dublin_core_refined=dc,
        graph_ui_community_overlay=graph_ui,
        leiden_quality_audit=audit,
    )
    quality = check_quality(
        report,
        QualityThresholds(
            require_page_count=2,
            min_communities=2,
            min_hydrated_communities=1,
            max_missing_page_membership=1,
            max_missing_category_summary=1,
            require_leiden_quality_pass=True,
            require_category_overlay_quality_pass=True,
            require_dublin_core_quality_pass=True,
        ),
    )
    assert quality["quality_status"] == "PASS"


def test_quality_fails_when_hydration_too_low():
    leiden, category_overlay, taxonomy, dc, graph_ui, audit = sample_inputs()
    report = build_hydrator_report(
        leiden_communities=leiden,
        category_aware_leiden_overlay=category_overlay,
        element_category_taxonomy=taxonomy,
        dublin_core_refined=dc,
        graph_ui_community_overlay=graph_ui,
        leiden_quality_audit=audit,
    )
    quality = check_quality(report, QualityThresholds(min_communities=2, min_hydrated_communities=2))
    assert quality["quality_status"] == "FAIL"
    assert any("hydrated_count" in issue for issue in quality["issues"])


def test_overlay_community_records_can_supply_categories_without_page_profiles():
    leiden = {"quality_status": "PASS", "communities": [{"community_id": "c1", "page_ids": ["t_p_120_1176_p000001"]}]}
    overlay = {
        "quality_status": "PASS",
        "community_cards": [{"community_id": "c1", "category_distribution": {"diagram": 2, "part": 1}}],
    }
    report = build_hydrator_report(
        leiden_communities=leiden,
        category_aware_leiden_overlay=overlay,
        element_category_taxonomy={"quality_status": "PASS"},
        dublin_core_refined={"quality_status": "PASS"},
    )
    record = report["community_hydration_records"][0]
    assert record["category_summary_hydrated"] is True
    assert record["dominant_category"] == "visual_evidence"
