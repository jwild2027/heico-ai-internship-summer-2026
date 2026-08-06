"""Patch 2 reproduction — best-PSM selection must be role-based, not volume-based.

The scan pack chose its primary OCR attempt with ``score = len(tokens) + 15 *
len(part_numbers)``. On diagram/grid pages, PSM 6/11 emit many isolated callout
numbers and therefore *win by volume*, replacing the cleaner PSM 3 caption/prose
text and poisoning downstream routing.

The new ``_select_primary_attempt`` keeps PSM 3 as the primary whole-page reader
by role, retains PSM 11/6 as supplemental attempts (never discarded), emits
component metrics and reason codes, and only lets another attempt win on
explicit, testable grounds (PSM 3 unusable, or a genuinely higher-confidence
attempt) — never on length alone.
"""
from tiff.trace_net_ocr_route_scan_pack_v1 import _select_primary_attempt, _tokens

PART = "120-41824-001"


def _attempt(psm, text, returncode=0, **extra):
    a = {"psm": psm, "returncode": returncode, "text": text}
    a.update(extra)
    return a


def _primary_psm(result):
    return result["metrics"][result["primary_index"]]["psm"]


def _old_volume_score(text):
    import re
    toks = _tokens(text)
    parts = set(re.findall(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", text))
    return len(toks) + 15 * len(parts)


def test_psm11_numeric_callouts_do_not_replace_psm3_prose():
    psm3 = _attempt(3, "Double Passenger Seat Figure 2 Installation and removal are described.")
    # PSM 11: many isolated diagram callout numbers + part numbers -> higher OLD score.
    psm11 = _attempt(11, "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 " + PART + " 120-41825-001")
    # Document the defect: the old volume rule would have picked PSM 11.
    assert _old_volume_score(psm11["text"]) > _old_volume_score(psm3["text"])
    result = _select_primary_attempt([psm3, psm11])
    assert _primary_psm(result) == 3
    assert "psm3_primary_by_role" in result["reason_codes"]


def test_psm11_callout_text_is_retained_as_supplemental():
    psm3 = _attempt(3, "Figure 3 seat assembly caption text here present.")
    psm11 = _attempt(11, "7 8 9 " + PART)
    result = _select_primary_attempt([psm3, psm11])
    supp = {result["metrics"][i]["psm"] for i in result["supplemental_indexes"]}
    assert 11 in supp  # supplemental attempt preserved, not discarded


def test_normal_procedure_page_stays_psm3_primary():
    psm3 = _attempt(3, "Remove the four bolts. Install the new leg structure and torque to spec.")
    psm6 = _attempt(6, "Remove four bolts Install new leg structure torque spec extra noise 12 13")
    result = _select_primary_attempt([psm3, psm6])
    assert _primary_psm(result) == 3


def test_empty_grid_noise_is_not_promoted_over_empty_psm3():
    # Page-508-like: PSM 3 empty; PSM 6 invents grid tokens (mostly punctuation/short).
    psm3 = _attempt(3, "")
    psm6 = _attempt(6, "| | | | - - - . . . | | 1 | | . .")
    result = _select_primary_attempt([psm3, psm6])
    assert _primary_psm(result) == 3  # noisy grid text must not win by length
    assert any("no_real_text" in c or "not_promoted" in c for c in result["reason_codes"])


def test_failed_attempt_cannot_win():
    psm3 = _attempt(3, "", returncode=1)  # failed
    psm11 = _attempt(11, "Genuine caption text that reads cleanly here.", returncode=0)
    result = _select_primary_attempt([psm3, psm11])
    assert result["metrics"][result["primary_index"]]["ok"] is True
    assert _primary_psm(result) == 11  # psm3 failed -> usable psm11 fallback


def test_higher_confidence_structured_attempt_can_beat_weak_psm3():
    # A genuinely structured, high-confidence attempt beats a weak/low-confidence PSM 3.
    psm3 = _attempt(3, "smudged prose line one", mean_confidence=42.0)
    psm6 = _attempt(6, "ITEM PART NUMBER NOMENCLATURE QTY aligned rows of the parts list",
                    mean_confidence=93.0)
    result = _select_primary_attempt([psm3, psm6])
    assert _primary_psm(result) == 6
    assert any("higher_confidence_override" in c for c in result["reason_codes"])


def test_confidence_metadata_is_honest_without_tsv():
    # No confidence supplied (the real Tesseract stdout path): must report unavailable.
    result = _select_primary_attempt([_attempt(3, "Plain caption text present."),
                                      _attempt(11, "1 2 3")])
    assert result["confidence_available"] is False
    assert result["selection_policy"] == "psm_role_without_tsv_confidence"


def test_confidence_metadata_reflects_supplied_confidence():
    result = _select_primary_attempt([_attempt(3, "Weak line", mean_confidence=40.0),
                                      _attempt(6, "ITEM PART NUMBER QTY aligned rows here", mean_confidence=92.0)])
    assert result["confidence_available"] is True
    assert result["selection_policy"] == "psm_role_with_tsv_confidence"


def test_metrics_and_reason_codes_are_emitted():
    psm3 = _attempt(3, "Caption text here present clearly.")
    psm11 = _attempt(11, "1 2 3")
    result = _select_primary_attempt([psm3, psm11])
    assert result["reason_codes"], "expected explicit selection reason codes"
    m = result["metrics"][0]
    for key in ("psm", "role", "ok", "word_count", "isolated_numeric_ratio",
                "garbage_ratio", "has_real_text"):
        assert key in m
    assert result["metrics"][1]["isolated_numeric_ratio"] > 0.5  # PSM 11 flagged numeric-heavy
