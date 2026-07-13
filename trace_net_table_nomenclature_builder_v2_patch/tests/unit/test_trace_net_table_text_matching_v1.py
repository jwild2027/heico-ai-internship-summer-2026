from tiff.trace_net_e2e_live_orchestrator_endpoint_v25 import _target_matches_value


def test_table_text_matching_is_order_insensitive_for_nomenclature():
    matched, reason, score = _target_matches_value("LOCKING RING", "RING, LOCKING", "table_text")
    assert matched is True
    assert reason == "target_tokens_in_value_any_order"
    assert score > 0


def test_part_number_matching_stays_exact_not_fuzzy():
    matched, reason, score = _target_matches_value("120-48024-001", "120-48024-002", "part_number")
    assert matched is False
    assert score == 0
