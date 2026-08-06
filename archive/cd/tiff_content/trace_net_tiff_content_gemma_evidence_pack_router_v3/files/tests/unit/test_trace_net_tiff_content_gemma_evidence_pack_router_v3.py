import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/operations/context/run_trace_net_tiff_content_gemma_evidence_pack_router_v3.py"
spec = importlib.util.spec_from_file_location("router_v3", SCRIPT)
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


def test_index_extracts_page_id_from_source_path(tmp_path):
    root = tmp_path / "trace_net"
    p = root / "raw_to_answer_context_engineered_native_gemma4_001" / "ocr_route_scan_pack_tesseract_full" / "ocr_text" / "t_p_120_1176_p000468.txt"
    p.parent.mkdir(parents=True)
    p.write_text("Removal of Seat Bottom (20) and Seat Backrest (30).", encoding="utf-8")
    rows = mod.build_local_index(root, max_files=20, max_file_bytes=10000, max_records=100)
    assert any("t_p_120_1176_p000468" in r.page_ids for r in rows)


def test_deterministic_ata_answer_uses_ata_and_pages():
    evidence = [
        rec("Document title: EMB CMM ATA 25-21-00 REV.4", "page_context/t_p_120_1176_p000001.json"),
        rec("Title contains ATA 25-21-00 and EMBRAER COMPONENT MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST", "page_context/t_p_120_1176_p000005.json"),
    ]
    ans = mod.deterministic_answer("I need an ATA number that starts with 2. What page and document is that?", "ata_identifier", evidence)
    assert ans is not None
    assert "25-21-00" in ans
    assert "t_p_120_1176_p000001" in ans or "t_p_120_1176_p000005" in ans
    assert "Direct answer:" in ans


def test_blank_answer_uses_deterministic_fallback():
    draft = "Direct answer: ATA 25-21-00.\nSource-trace status: Source-traceable.\nEvidence used: E1.\nMissing evidence / limits: None."
    ans, used = mod.normalize_answer("", question="What ATA number?", route="ata_identifier", evidence_count=1, deterministic_draft=draft)
    assert used is True
    assert ans == draft


def test_document_title_and_revision_answers():
    evidence = [rec("source_package_summary.title: EMB CMM ATA 25-21-00 REV.4; revision date 10 April 2006; EMBRAER COMPONENT MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST")]
    title = mod.deterministic_answer("What document title is associated with the scanned pages?", "document_title", evidence)
    rev = mod.deterministic_answer("What revision is associated with the scanned document?", "document_revision", evidence)
    assert title and "COMPONENT MAINTENANCE MANUAL" in title
    assert rev and "Revision 4" in rev and "10 April 2006" in rev


def test_figure_target_page_and_nomenclature():
    evidence = [
        rec("Visual evidence links Figure 69 to part number 120-50645-005 on page 315", "visual/t_p_120_1176_p000315.json"),
        rec("69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF", "ocr/t_p_120_1176_p000316.txt"),
    ]
    ans = mod.deterministic_answer("Which page contains Figure 69?", "figure_visual", evidence)
    assert ans and "Figure 69" in ans and "p000315" in ans
    ans2 = mod.deterministic_answer("What does Figure 69 appear to show?", "figure_visual", evidence)
    assert ans2 and "120-50645-005" in ans2


def test_manual_keyword_does_not_use_pipeline_warning_tokens():
    bad = rec("anchor_aware_warnings: warning fields only", "pipeline/t_p_120_1176_p000001.json")
    good = rec("WARNING: Obey the safety precautions before cleaning.", "ocr/t_p_120_1176_p000470.txt")
    assert not mod.record_passes_route(bad, "Which pages mention warnings?", "manual_keyword")
    assert mod.record_passes_route(good, "Which pages mention warnings?", "manual_keyword")
