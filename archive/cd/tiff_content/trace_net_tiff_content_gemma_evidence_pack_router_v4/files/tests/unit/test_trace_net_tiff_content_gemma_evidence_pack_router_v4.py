import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/operations/context/run_trace_net_tiff_content_gemma_evidence_pack_router_v4.py"
spec = importlib.util.spec_from_file_location("router_v4", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def rec(text, source="ocr_text/t_p_120_1176_p000001.txt"):
    combined = f"{source} {text}"
    return mod.EvidenceRecord(
        source_path=source,
        line_no=1,
        text=text,
        page_ids=tuple(sorted(set(m.group(0) for m in mod.PAGE_ID_RE.finditer(combined)))),
        part_numbers=tuple(sorted(set(m.group(0) for m in mod.PART_RE.finditer(text)))),
        ata_numbers=tuple(sorted(set(m.group(0) for m in mod.ATA_RE.finditer(combined)))),
        figure_refs=tuple(sorted(set(m.group(0) for m in mod.FIGURE_RE.finditer(combined)))),
        score=10.0,
    )


def test_classifies_exact_part_nomenclature_before_generic_nomenclature():
    assert mod.classify_question("What nomenclature is associated with part number 120-36833-001?") == "part_nomenclature"


def test_part_nomenclature_finds_single_passenger_seat():
    evidence = [
        rec("Single Passenger Seat (120-36833-001)", "ocr/t_p_120_1176_p000145.txt"),
        rec("120-36833-001 SINGLE PASSENGER SEAT ASSY ............ VS4956 | 028/034; REF", "ocr/t_p_120_1176_p000146.txt"),
    ]
    ans = mod.deterministic_answer("What nomenclature is associated with part number 120-36833-001?", "part_nomenclature", evidence)
    assert ans is not None
    assert "120-36833-001" in ans
    assert "SINGLE PASSENGER SEAT" in ans.upper()
    assert "eligibility" in ans.lower()


def test_malformed_partial_answer_uses_deterministic_fallback():
    draft = "Direct answer: Figure 69 is associated with part number 120-50645-005.\nSource-trace status: Source-traceable.\nEvidence used: E1.\nMissing evidence / limits: None."
    ans, used = mod.normalize_answer(
        "Direct answer: Figure 69 is linked to part number 120-",
        question="What does Figure 69 appear to show?",
        route="figure_visual",
        evidence_count=3,
        deterministic_draft=draft,
    )
    assert used is True
    assert ans == draft


def test_figure_page_prefers_visual_page_number_and_mentions_support_page():
    evidence = [
        rec("Visual evidence links Figure 69 to part number 120-50645-005 on page 315", "visual/t_p_120_1176_p000315.json"),
        rec("69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF", "ocr/t_p_120_1176_p000316.txt"),
    ]
    ans = mod.deterministic_answer("Which page contains Figure 69?", "figure_visual", evidence)
    assert ans and "page 315" in ans
    assert "p000316" in ans or "Supporting" in ans


def test_strict_part_filter_removes_ata_page_counters_and_junk():
    evidence = [rec("part_number_tokens: 1001 1002 25-21-00 u2026 120-46137-001", "ocr/t_p_120_1176_p000339.txt")]
    parts = mod.evidence_parts(evidence)
    assert "120-46137-001" in parts
    assert "25-21-00" not in parts
    assert "1001" not in parts
    assert "u2026" not in [p.lower() for p in parts]


def test_extraction_issue_route_and_answer_pages():
    assert mod.classify_question("Which pages appear to have low-confidence OCR or extraction issues?") == "extraction_issue"
    evidence = [rec("low_confidence_visual_candidate_count: 23 review_required", "quality/t_p_120_1176_p000092.json")]
    ans = mod.deterministic_answer("Which pages appear to have low-confidence OCR or extraction issues?", "extraction_issue", evidence)
    assert ans and "p000092" in ans


def test_source_trace_claims_route_summary():
    assert mod.classify_question("Which claims in this document are source-trace-ready from citations?") == "source_trace_claims"
    evidence = [
        rec("source_trace_ready true citation_ready true covered_part_number 120-36833-001", "citations/t_p_120_1176_p000003.json"),
        rec("source_trace_ready true citation_ready true ATA 25-21-00", "citations/t_p_120_1176_p000005.json"),
    ]
    ans = mod.deterministic_answer("Which claims in this document are source-trace-ready from citations?", "source_trace_claims", evidence)
    assert ans and "claim categories" in ans
    assert "120-36833-001" in ans
    assert "25-21-00" in ans


def test_structured_page_question_uses_deterministic_direct():
    draft = "Direct answer: Pages with selected visual/callout/label evidence include page 315 (t_p_120_1176_p000315).\nSource-trace status: Source-traceable.\nEvidence used: E1.\nMissing evidence / limits: Selected snippets only."
    assert mod.should_use_deterministic_direct("Which pages have visual evidence for part numbers?", "visual", draft)
