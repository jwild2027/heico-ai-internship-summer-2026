from tiff.trace_net_leiden_community_quality_audit_v1 import (
    PASS,
    QualityThresholds,
    build_leiden_community_quality_audit,
    check_leiden_community_quality_audit,
    collect_page_ids,
    community_id_of,
    extract_ata_codes,
    extract_part_numbers,
    summary_count,
    write_json,
)


def sample_leiden():
    return {
        "quality_status": "PASS",
        "summary": {
            "community_count": 2,
            "page_node_count": 509,
            "graph_node_count": 32446,
            "graph_edge_count": 35907,
            "orphan_edge_count": 0,
            "community_as_proof_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "communities": [
            {
                "community_id": "c1",
                "label": "Part family community 120-46137",
                "page_ids": ["t_p_120_1176_p000003", "t_p_120_1176_p000340"],
                "part_numbers": ["120-46137-001"],
                "category_counts": {"part": 10, "table": 4},
            },
            {
                "community_id": "c2",
                "label": "Review cluster ATA 25-21-00",
                "page_ids": ["t_p_120_1176_p000050"],
                "category_counts": {"source": 9},
            },
        ],
    }


def sample_category_overlay():
    return {
        "quality_status": "PASS",
        "summary": {
            "community_count": 2,
            "page_category_profile_count": 509,
            "category_as_proof_count": 0,
        },
    }


def test_collect_page_ids_nested():
    value = {"source_trace": {"page_ids": ["t_p_120_1176_p000003"]}, "text": "see t_p_120_1176_p000004"}
    assert collect_page_ids(value) == ["t_p_120_1176_p000003", "t_p_120_1176_p000004"]


def test_extract_identifiers():
    record = {"label": "ATA 25-21-00 part 120-46137-001", "parts": ["120-46137-501"]}
    assert extract_ata_codes(record) == ["25-21-00"]
    assert extract_part_numbers(record) == ["120-46137-001", "120-46137-501"]


def test_community_id_fallback():
    assert community_id_of({}, 7) == "community_00007"
    assert community_id_of({"community_id": "abc"}, 1) == "abc"


def test_summary_count_alias():
    assert summary_count({"summary": {"leiden_community_count": 229}}, "community_count") == 229


def test_build_audit_passes_with_safe_records():
    report = build_leiden_community_quality_audit(
        leiden_communities=sample_leiden(),
        category_aware_leiden_overlay=sample_category_overlay(),
        thresholds=QualityThresholds(
            require_page_count=509,
            min_communities=2,
            min_audit_records=2,
            require_leiden_quality_pass=True,
            require_category_overlay_quality_pass=True,
            require_no_orphan_edges=True,
        ),
    )
    assert report["quality_status"] == PASS
    summary = report["summary"]
    assert summary["leiden_community_count"] == 2
    assert summary["community_audit_record_count"] == 2
    assert summary["community_as_proof_count"] == 0
    assert summary["category_as_proof_count"] == 0
    assert summary["can_answer_directly_count"] == 0
    assert summary["can_prove_claims_count"] == 0


def test_build_audit_flags_policy_leak():
    leiden = sample_leiden()
    leiden["communities"][0]["can_prove_claims"] = True
    report = build_leiden_community_quality_audit(
        leiden_communities=leiden,
        category_aware_leiden_overlay=sample_category_overlay(),
        thresholds=QualityThresholds(min_communities=2, min_audit_records=2, max_unsafe_records=0),
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["unsafe_community_record_count"] == 1


def test_placeholder_records_when_only_counts_exist():
    leiden = {"quality_status": "PASS", "summary": {"community_count": 3, "page_count": 509}}
    report = build_leiden_community_quality_audit(
        leiden_communities=leiden,
        thresholds=QualityThresholds(require_page_count=509, min_communities=3, min_audit_records=3),
    )
    assert report["quality_status"] == PASS
    assert report["summary"]["count_only_record_count"] == 3
    assert len(report["community_audit_records"]) == 3


def test_quality_check_writes_quality_json(tmp_path):
    report = build_leiden_community_quality_audit(
        leiden_communities=sample_leiden(),
        category_aware_leiden_overlay=sample_category_overlay(),
        thresholds=QualityThresholds(require_page_count=509, min_communities=2, min_audit_records=2),
    )
    path = tmp_path / "trace_net_leiden_community_quality_audit_v1.json"
    write_json(path, report)
    checked = check_leiden_community_quality_audit(
        report_path=path,
        thresholds=QualityThresholds(require_page_count=509, min_communities=2, min_audit_records=2),
        write_json_report=True,
    )
    assert checked["quality_status"] == PASS
    assert path.with_name("trace_net_leiden_community_quality_audit_v1_quality.json").exists()
