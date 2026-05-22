"""tests/unit/test_stage1_digestion.py — Stage 1: PDF Digestion (50 tests)

Tests bench.extract_pages_pymupdf() output directly.
No LLM, no Qdrant, no DB required.

Usage:
    pytest tests/unit/test_stage1_digestion.py -v \
        --pdf-test2 "path/to/test-2.pdf" \
        --pdf-test3 "path/to/test-3.pdf"

Optional flags:
    --pdf-test2   Path to the seaplane handbook PDF   (default: test-2.pdf)
    --pdf-test3   Path to the sUAS study guide PDF    (default: test-3.pdf)
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import pytest




# ---------------------------------------------------------------------------
# Fixtures — extracted once per session, reused by all tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pdf_path_2(request) -> Path:
    p = Path(request.config.getoption("--pdf-test2")).resolve()
    if not p.exists():
        pytest.skip(f"test-2 PDF not found at {p}")
    return p


@pytest.fixture(scope="session")
def pdf_path_3(request) -> Path:
    p = Path(request.config.getoption("--pdf-test3")).resolve()
    if not p.exists():
        pytest.skip(f"test-3 PDF not found at {p}")
    return p


@pytest.fixture(scope="session")
def pages_2(pdf_path_2) -> list[dict[str, Any]]:
    """Extract pages from test-2 once for the whole session."""
    import rag_benchmark as bench
    return bench.extract_pages_pymupdf(
        pdf_path_2,
        debug_dir=Path("ocr_debug"),
        ocr_debug=True,
        save_images=False,
    )


@pytest.fixture(scope="session")
def pages_3(pdf_path_3) -> list[dict[str, Any]]:
    """Extract pages from test-3 once for the whole session."""
    import rag_benchmark as bench
    return bench.extract_pages_pymupdf(
        pdf_path_3,
        debug_dir=Path("ocr_debug"),
        ocr_debug=True,
        save_images=False,
    )


@pytest.fixture(scope="session")
def full_text_2(pages_2) -> str:
    return " ".join(p["text"] for p in pages_2).lower()


@pytest.fixture(scope="session")
def full_text_3(pages_3) -> str:
    return " ".join(p["text"] for p in pages_3).lower()


@pytest.fixture(scope="session")
def page_map_2(pages_2) -> dict[int, dict]:
    """page_number → page dict for test-2."""
    return {p["page"]: p for p in pages_2}


@pytest.fixture(scope="session")
def page_map_3(pages_3) -> dict[int, dict]:
    """page_number → page dict for test-3."""
    return {p["page"]: p for p in pages_3}


# ---------------------------------------------------------------------------
# Known-blank pages in test-3 (from your ingest logs)
# ---------------------------------------------------------------------------
KNOWN_BLANK_PAGES_TEST3 = [2, 10, 12, 80, 83, 85]

# Required keys every page dict must expose
REQUIRED_PAGE_KEYS = [
    "page", "text", "native_text", "ocr_text",
    "ocr_used", "ocr_quality", "ocr_confidence",
]

# Ground-truth terms that MUST appear somewhere in the full document text
GROUND_TRUTH_TEST2 = [
    "sponson", "water rudder", "glassy water", "hydrodynamic",
    "right-of-way", "91.115", "flying boat", "floatplane",
]
GROUND_TRUTH_TEST3 = [
    "class b", "density altitude", "hazardous attitudes",
    "hyperventilation", "imsafe", "thunderstorm", "notam",
    "122.9",
]


# ===========================================================================
# TEST 1 — Native text non-empty on known content page
# ===========================================================================
def test_01_native_text_nonempty_on_content_page(pages_3):
    """Pages with high quality score must have non-empty native text."""
    content_pages = [p for p in pages_3 if p.get("ocr_quality", 0) >= 0.80]
    assert content_pages, "No high-quality pages found"
    for p in content_pages[:10]:
        assert len(p["native_text"].strip()) > 50, (
            f"Page {p['page']}: native_text too short "
            f"({len(p['native_text'].strip())} chars)"
        )


# ===========================================================================
# TEST 2 — Word count sanity on body pages
# ===========================================================================
def test_02_word_count_sanity_on_body_pages(pages_3):
    """Non-blank, high-quality pages must have at least 20 words."""
    body_pages = [
        p for p in pages_3
        if p.get("ocr_quality", 0) >= 0.80
        and p["page"] not in KNOWN_BLANK_PAGES_TEST3
    ]
    assert body_pages, "No body pages found"
    for p in body_pages[:15]:
        wc = len(p["text"].split())
        assert wc >= 20, f"Page {p['page']}: only {wc} words in selected text"


# ===========================================================================
# TEST 3 — Ground truth: "sponson" in test-2
# ===========================================================================
def test_03_ground_truth_sponson_in_test2(full_text_2):
    assert "sponson" in full_text_2, \
        "'sponson' not found anywhere in test-2 full text"


# ===========================================================================
# TEST 4 — Ground truth: "class b" in test-3
# ===========================================================================
def test_04_ground_truth_classb_in_test3(full_text_3):
    assert "class b" in full_text_3, \
        "'class b' not found anywhere in test-3 full text"


# ===========================================================================
# TEST 5 — No leading/trailing whitespace on selected text
# ===========================================================================
def test_05_no_leading_trailing_whitespace(pages_3):
    for p in pages_3:
        text = p["text"]
        assert text == text.strip(), (
            f"Page {p['page']}: selected text has leading/trailing whitespace"
        )


# ===========================================================================
# TEST 6 — No consecutive duplicate lines (header/footer loop detection)
# ===========================================================================
def test_06_no_consecutive_duplicate_lines(pages_3):
    for p in pages_3:
        lines = [l for l in p["text"].splitlines() if l.strip()]
        for i in range(len(lines) - 3):
            window = lines[i:i+4]
            assert len(set(window)) > 1, (
                f"Page {p['page']}: line '{lines[i]}' repeated 4+ times consecutively"
            )


# ===========================================================================
# TEST 7 — page field is a positive integer
# ===========================================================================
def test_07_page_field_is_positive_integer(pages_2, pages_3):
    for p in pages_2 + pages_3:
        assert isinstance(p["page"], int), \
            f"page field is {type(p['page'])}, expected int"
        assert p["page"] >= 1, f"page number {p['page']} is < 1"


# ===========================================================================
# TEST 8 — Pages are returned in strictly ascending order
# ===========================================================================
def test_08_pages_ascending_order(pages_2, pages_3):
    for doc_label, pages in [("test-2", pages_2), ("test-3", pages_3)]:
        for i in range(1, len(pages)):
            assert pages[i]["page"] == pages[i-1]["page"] + 1, (
                f"{doc_label}: page order broken between "
                f"{pages[i-1]['page']} and {pages[i]['page']}"
            )


# ===========================================================================
# TEST 9 — Total page count matches known value for test-3
# ===========================================================================
def test_09_page_count_test3(pages_3):
    # From your ingest logs: 88 pages
    assert len(pages_3) == 88, \
        f"test-3 expected 88 pages, got {len(pages_3)}"


# ===========================================================================
# TEST 10 — Total page count for test-2 is a plausible non-zero value
# ===========================================================================
def test_10_page_count_test2_nonzero(pages_2):
    assert len(pages_2) > 0, "test-2 returned 0 pages"
    assert len(pages_2) < 500, f"test-2 returned implausibly many pages: {len(pages_2)}"


# ===========================================================================
# TEST 11 — Known blank pages produce minimal text
# ===========================================================================
def test_11_blank_pages_minimal_text(page_map_3):
    for pnum in KNOWN_BLANK_PAGES_TEST3:
        if pnum not in page_map_3:
            continue
        p = page_map_3[pnum]
        wc = len(p["text"].strip().split())
        assert wc < 20, (
            f"Page {pnum} is known blank but has {wc} words: "
            f"'{p['text'][:100]}'"
        )


# ===========================================================================
# TEST 12 — Blank pages don't contain body content words
# ===========================================================================
def test_12_blank_pages_no_body_content(page_map_3):
    body_terms = ["airspace", "sponson","water",
                  "altitude", "weather", "takeoff", "landing"]
    for pnum in KNOWN_BLANK_PAGES_TEST3:
        if pnum not in page_map_3:
            continue
        text = page_map_3[pnum]["text"].lower()
        found = [t for t in body_terms if t in text]
        assert not found, (
            f"Page {pnum} (known blank) contains body terms: {found}"
        )


# ===========================================================================
# TEST 13 — All required keys present on every page
# ===========================================================================
def test_13_required_keys_present(pages_2, pages_3):
    for doc_label, pages in [("test-2", pages_2), ("test-3", pages_3)]:
        for p in pages:
            missing = [k for k in REQUIRED_PAGE_KEYS if k not in p]
            assert not missing, (
                f"{doc_label} page {p.get('page','?')}: missing keys {missing}"
            )


# ===========================================================================
# TEST 14 — ocr_quality is a float between 0.0 and 1.0
# ===========================================================================
def test_14_ocr_quality_range(pages_3):
    for p in pages_3:
        q = p["ocr_quality"]
        assert isinstance(q, float), \
            f"Page {p['page']}: ocr_quality is {type(q)}, expected float"
        assert 0.0 <= q <= 1.0, \
            f"Page {p['page']}: ocr_quality={q} out of range [0.0, 1.0]"


# ===========================================================================
# TEST 15 — ocr_confidence is a float between 0.0 and 100.0
# ===========================================================================
def test_15_ocr_confidence_range(pages_3):
    for p in pages_3:
        c = p["ocr_confidence"]
        assert isinstance(c, float), \
            f"Page {p['page']}: ocr_confidence is {type(c)}, expected float"
        assert 0.0 <= c <= 100.0, \
            f"Page {p['page']}: ocr_confidence={c} out of range [0.0, 100.0]"


# ===========================================================================
# TEST 16 — ocr_used is a bool (not int 0/1, not string)
# ===========================================================================
def test_16_ocr_used_is_bool(pages_3):
    for p in pages_3:
        val = p["ocr_used"]
        assert isinstance(val, bool), (
            f"Page {p['page']}: ocr_used={val!r} is {type(val)}, expected bool"
        )


# ===========================================================================
# TEST 17 — Selected text non-empty on all content pages
# ===========================================================================
def test_17_selected_text_nonempty_on_content_pages(pages_3):
    content_pages = [
        p for p in pages_3
        if p["page"] not in KNOWN_BLANK_PAGES_TEST3
        and p.get("ocr_quality", 0) >= 0.60
    ]
    for p in content_pages:
        assert len(p["text"].strip()) > 0, \
            f"Page {p['page']}: selected text is empty on a content page"


# ===========================================================================
# TEST 18 — Selected text derives from one of the extraction outputs
# ===========================================================================
def test_18_selected_text_derives_from_extraction(pages_3):
    """Selected text must share a 20-char substring with native or OCR text."""
    for p in pages_3:
        selected = p["text"].strip()
        if len(selected) < 20:
            continue  # blank/near-blank page — skip
        native = p.get("native_text", "")
        ocr    = p.get("ocr_text", "")
        probe  = selected[:20]
        assert (probe in native) or (probe in ocr), (
            f"Page {p['page']}: selected text start '{probe}' not found in "
            f"native or OCR text — possible phantom text"
        )


# ===========================================================================
# TEST 19 — Degree symbol survives extraction
# ===========================================================================
def test_19_degree_symbol_survives(full_text_3):
    # sUAS guide has temperature content
    has_degree = "°" in full_text_3
    has_word   = "degree" in full_text_3
    assert has_degree or has_word, \
        "Neither '°' nor 'degree' found in test-3 — temperature content may be garbled"


# ===========================================================================
# TEST 20 — Fractional values survive extraction
# ===========================================================================
def test_20_fractions_survive(full_text_3):
    # sUAS guide contains values like "1/2", frequencies like "122.9"
    assert re.search(r'\d+/\d+|\d+\.\d+', full_text_3), \
        "No fractions or decimal numbers found in test-3 text"


# ===========================================================================
# TEST 21 — Hyphenated terms survive extraction
# ===========================================================================
def test_21_hyphenated_terms_survive(full_text_2):
    assert "right-of-way" in full_text_2, \
        "'right-of-way' not found in test-2 — hyphens may be stripped"


# ===========================================================================
# TEST 22 — Frequency value "122.9" survives extraction
# ===========================================================================
def test_22_frequency_value_survives(full_text_3):
    assert "122.9" in full_text_3, \
        "'122.9' (MULTICOM frequency) not found in test-3"


# ===========================================================================
# TEST 23 — Regulatory citation "91.115" survives extraction
# ===========================================================================
def test_23_regulatory_citation_survives(full_text_2):
    assert "91.115" in full_text_2, \
        "'91.115' (FAR citation) not found in test-2"


# ===========================================================================
# TEST 24 — Table content not garbled (no runs of single-char tokens)
# ===========================================================================
def test_24_table_content_not_garbled(pages_3):
    """Detect column-by-column extraction: 5+ consecutive single-char tokens."""
    for p in pages_3:
        tokens = p["text"].split()
        if len(tokens) < 10:
            continue
        for i in range(len(tokens) - 5):
            window = tokens[i:i+5]
            all_single = all(len(t) == 1 for t in window)
            assert not all_single, (
                f"Page {p['page']}: 5 consecutive single-char tokens detected "
                f"at position {i}: {window} — likely garbled table"
            )


# ===========================================================================
# TEST 25 — Header "Remote Pilot" appears at most once per page text
# ===========================================================================
def test_25_running_header_not_duplicated(pages_3):
    """The running header should not appear on blank pages where there is
    no body content — that would indicate header bleed into empty pages."""
    for pnum in KNOWN_BLANK_PAGES_TEST3:
        if pnum not in {p["page"]: p for p in pages_3}:
            continue
        page_map = {p["page"]: p for p in pages_3}
        text = page_map[pnum]["text"].lower()
        # Blank pages may have the header once but not body repetition
        count = text.count("remote pilot")
        assert count <= 1, (
            f"Page {pnum} (blank): 'remote pilot' appears {count} times — "
            f"header duplicated into blank page body"
        )


# ===========================================================================
# TEST 26 — Bare page number footer not included as standalone token
# ===========================================================================
def test_26_page_number_footer_not_in_body(page_map_3):
    """The bare page number (e.g. just '72') should not appear as a
    standalone line in the middle of body text."""
    for pnum, p in page_map_3.items():
        lines = p["text"].splitlines()
        # Ignore first and last 2 lines (headers/footers expected there)
        body_lines = lines[2:-2]
        for line in body_lines:
            stripped = line.strip()
            if stripped == str(pnum):
                pytest.fail(
                    f"Page {pnum}: bare page number '{pnum}' found as "
                    f"standalone line in body text"
                )


# ===========================================================================
# TEST 27 — OCR text populated when OCR ran
# ===========================================================================
def test_27_ocr_text_populated_when_ocr_ran(pages_3):
    ocr_pages = [p for p in pages_3 if p["ocr_used"]]
    assert ocr_pages, "No OCR pages found in test-3 — expected at least 7"
    for p in ocr_pages:
        assert len(p["ocr_text"].strip()) > 0, (
            f"Page {p['page']}: ocr_used=True but ocr_text is empty"
        )


# ===========================================================================
# TEST 28 — native_text field present even when OCR selected
# ===========================================================================
def test_28_native_text_present_even_when_ocr_selected(pages_3):
    ocr_pages = [p for p in pages_3 if p["ocr_used"]]
    for p in ocr_pages:
        assert p["native_text"] is not None, (
            f"Page {p['page']}: native_text is None when ocr_used=True — "
            f"must be empty string, not None"
        )


# ===========================================================================
# TEST 29 — No None values in any text field
# ===========================================================================
def test_29_no_none_in_text_fields(pages_2, pages_3):
    text_keys = ["text", "native_text", "ocr_text"]
    for doc_label, pages in [("test-2", pages_2), ("test-3", pages_3)]:
        for p in pages:
            for key in text_keys:
                assert p[key] is not None, (
                    f"{doc_label} page {p['page']}: {key} is None"
                )


# ===========================================================================
# TEST 30 — No exception on test-2 extraction
# ===========================================================================
def test_30_no_exception_test2(pdf_path_2):
    import rag_benchmark as bench
    try:
        pages = bench.extract_pages_pymupdf(
            pdf_path_2,
            debug_dir=Path("ocr_debug"),
            ocr_debug=False,
            save_images=False,
        )
        assert len(pages) > 0
    except Exception as e:
        pytest.fail(f"extract_pages_pymupdf raised on test-2: {e}")


# ===========================================================================
# TEST 31 — No exception on test-3 extraction
# ===========================================================================
def test_31_no_exception_test3(pdf_path_3):
    import rag_benchmark as bench
    try:
        pages = bench.extract_pages_pymupdf(
            pdf_path_3,
            debug_dir=Path("ocr_debug"),
            ocr_debug=False,
            save_images=False,
        )
        assert len(pages) > 0
    except Exception as e:
        pytest.fail(f"extract_pages_pymupdf raised on test-3: {e}")


# ===========================================================================
# TEST 32 — FileNotFoundError on missing PDF
# ===========================================================================
def test_32_file_not_found_raises_clearly():
    import rag_benchmark as bench
    with pytest.raises((FileNotFoundError, Exception)) as exc_info:
        bench.extract_pages_pymupdf(
            Path("nonexistent_file_abc123.pdf"),
            debug_dir=Path("ocr_debug"),
            ocr_debug=False,
            save_images=False,
        )
    # Must not be a bare AttributeError or NoneType crash
    assert exc_info.type is not AttributeError, \
        "Got AttributeError instead of FileNotFoundError — no path validation"


# ===========================================================================
# TEST 33 — Extraction completes test-3 in under 180 seconds
# ===========================================================================
def test_33_extraction_completes_within_time_limit(pdf_path_3):
    import rag_benchmark as bench
    t0 = time.perf_counter()
    bench.extract_pages_pymupdf(
        pdf_path_3,
        debug_dir=Path("ocr_debug"),
        ocr_debug=False,
        save_images=False,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 180, \
        f"test-3 extraction took {elapsed:.1f}s — exceeds 180s limit"


# ===========================================================================
# TEST 34 — Output is consistent across two calls (no randomness)
# ===========================================================================
def test_34_extraction_is_deterministic(pdf_path_3):
    import rag_benchmark as bench
    kwargs = dict(debug_dir=Path("ocr_debug"), ocr_debug=False, save_images=False)
    pages_a = bench.extract_pages_pymupdf(pdf_path_3, **kwargs)
    pages_b = bench.extract_pages_pymupdf(pdf_path_3, **kwargs)
    assert len(pages_a) == len(pages_b), "Page count differs between runs"
    for pa, pb in zip(pages_a, pages_b):
        assert pa["text"] == pb["text"], (
            f"Page {pa['page']}: text differs between runs — non-deterministic"
        )


# ===========================================================================
# TEST 35 — OCR quality higher on content pages vs blank pages
# ===========================================================================
def test_35_quality_higher_on_content_than_blank(pages_3):
    blank_quality = [
        pages_3[p-1]["ocr_quality"]
        for p in KNOWN_BLANK_PAGES_TEST3
        if p <= len(pages_3)
    ]
    content_quality = [
        p["ocr_quality"]
        for p in pages_3
        if p["page"] not in KNOWN_BLANK_PAGES_TEST3
        and p["ocr_quality"] > 0
    ]
    assert content_quality and blank_quality
    mean_content = sum(content_quality) / len(content_quality)
    mean_blank   = sum(blank_quality)   / len(blank_quality)
    assert mean_content > mean_blank, (
        f"Mean content quality {mean_content:.3f} not > "
        f"mean blank quality {mean_blank:.3f}"
    )


# ===========================================================================
# TEST 36 — OCR confidence >= 90 on known clean OCR pages
# ===========================================================================
def test_36_ocr_confidence_high_on_clean_pages(page_map_3):
    # From your logs: pages 10, 12, 80, 83, 85 had confidence 94.5–94.6
    known_ocr_pages = [10, 12, 80, 83, 85]
    for pnum in known_ocr_pages:
        if pnum not in page_map_3:
            continue
        p = page_map_3[pnum]
        conf = p["ocr_confidence"]
        assert conf >= 90.0, (
            f"Page {pnum}: expected confidence >= 90, got {conf}"
        )


# ===========================================================================
# TEST 37 — No cross-page text contamination
# ===========================================================================
def test_37_no_cross_page_text_contamination(pages_3):
    """Last 50 chars of page N must not appear at the start of page N+1."""
    for i in range(len(pages_3) - 1):
        if pages_3[i]["page"] <=10:
            continue
        tail   = pages_3[i]["text"].strip()[-50:]
        head   = pages_3[i+1]["text"].strip()[:50]
        if len(tail) < 10 or len(head) < 10:
            continue  # too short to test meaningfully
        assert tail not in pages_3[i+1]["text"], (
            f"Page {pages_3[i]['page']} tail found at start of page "
            f"{pages_3[i+1]['page']} — possible cross-page bleed"
        )


# ===========================================================================
# TEST 38 — At least 70% of pages have sufficient word count
# ===========================================================================
def test_38_majority_of_pages_have_content(pages_3):
    """Catches mass OCR failure — if most pages come back empty, pipeline is broken."""
    sufficient = sum(1 for p in pages_3 if len(p["text"].split()) >= 20)
    ratio = sufficient / len(pages_3)
    assert ratio >= 0.70, (
        f"Only {sufficient}/{len(pages_3)} ({ratio:.0%}) pages have >= 20 words — "
        f"mass extraction failure likely"
    )


# ===========================================================================
# TEST 39 — All ground truth terms present in test-2
# ===========================================================================
@pytest.mark.parametrize("term", GROUND_TRUTH_TEST2)
def test_39_ground_truth_terms_test2(term, full_text_2):
    assert term in full_text_2, \
        f"Ground truth term '{term}' not found anywhere in test-2"


# ===========================================================================
# TEST 40 — All ground truth terms present in test-3
# ===========================================================================
@pytest.mark.parametrize("term", GROUND_TRUTH_TEST3)
def test_40_ground_truth_terms_test3(term, full_text_3):
    assert term in full_text_3, \
        f"Ground truth term '{term}' not found anywhere in test-3"


# ===========================================================================
# TEST 41 — PDF path resolution: relative path becomes absolute
# ===========================================================================
def test_41_path_resolution_relative(pdf_path_3):
    import tools.pymupdf_bge_chroma_cli as base
    resolved = base.resolve_pdf_path(pdf_path_3)
    assert resolved.is_absolute(), \
        f"resolve_pdf_path returned non-absolute path: {resolved}"
    assert resolved.exists(), \
        f"resolve_pdf_path returned path that does not exist: {resolved}"


# ===========================================================================
# TEST 42 — PDF path resolution: absolute path unchanged
# ===========================================================================
def test_42_path_resolution_absolute(pdf_path_3):
    import tools.pymupdf_bge_chroma_cli as base
    absolute = pdf_path_3.resolve()
    resolved = base.resolve_pdf_path(absolute)
    assert resolved == absolute, \
        f"resolve_pdf_path changed absolute path: {absolute} → {resolved}"


# ===========================================================================
# TEST 43 — Return type is list of dicts
# ===========================================================================
def test_43_return_type_is_list_of_dicts(pages_3):
    assert isinstance(pages_3, list), \
        f"extract_pages_pymupdf returned {type(pages_3)}, expected list"
    assert all(isinstance(p, dict) for p in pages_3), \
        "Not all elements in pages list are dicts"


# ===========================================================================
# TEST 44 — All page numbers unique (no duplicates)
# ===========================================================================
def test_44_all_page_numbers_unique(pages_2, pages_3):
    for doc_label, pages in [("test-2", pages_2), ("test-3", pages_3)]:
        nums = [p["page"] for p in pages]
        assert len(set(nums)) == len(nums), (
            f"{doc_label}: duplicate page numbers found: "
            f"{[n for n in nums if nums.count(n) > 1]}"
        )


# ===========================================================================
# TEST 45 — "density altitude" in test-3
# ===========================================================================
def test_45_density_altitude_in_test3(full_text_3):
    assert "density altitude" in full_text_3, \
        "'density altitude' not found in test-3"


# ===========================================================================
# TEST 46 — "glassy water" in test-2
# ===========================================================================
def test_46_glassy_water_in_test2(full_text_2):
    assert "glassy water" in full_text_2, \
        "'glassy water' not found in test-2"


# ===========================================================================
# TEST 47 — "water rudder" in test-2
# ===========================================================================
def test_47_water_rudder_in_test2(full_text_2):
    assert "water rudder" in full_text_2, \
        "'water rudder' not found in test-2"


# ===========================================================================
# TEST 48 — "hazardous attitudes" in test-3
# ===========================================================================
def test_48_hazardous_attitudes_in_test3(full_text_3):
    assert "hazardous attitudes" in full_text_3, \
        "'hazardous attitudes' not found in test-3"


# ===========================================================================
# TEST 49 — ocr_used=False for high-quality pages in test-3
# ===========================================================================
def test_49_no_ocr_on_high_quality_pages(pages_3):
    """Pages with quality >= 0.83 (from your logs) should not trigger OCR."""
    high_quality = [
        p for p in pages_3
        if p["ocr_quality"] >= 0.83
        and p["page"] not in KNOWN_BLANK_PAGES_TEST3
    ]
    assert high_quality, "No high-quality pages found"
    for p in high_quality:
        assert p["ocr_used"] is False, (
            f"Page {p['page']}: quality={p['ocr_quality']:.2f} >= 0.83 "
            f"but ocr_used=True — OCR triggered unnecessarily"
        )


# ===========================================================================
# TEST 50 — Number of OCR-selected pages matches known value from logs
# ===========================================================================
def test_50_ocr_selected_page_count_matches_logs(pages_3):
    """Your ingest logs show exactly 7 OCR-selected pages in test-3."""
    ocr_count = sum(1 for p in pages_3 if p["ocr_used"])
    assert ocr_count == 7, (
        f"Expected 7 OCR-selected pages in test-3 (from ingest logs), "
        f"got {ocr_count}"
    )