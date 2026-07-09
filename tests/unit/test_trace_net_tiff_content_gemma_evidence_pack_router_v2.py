import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_trace_net_tiff_content_gemma_evidence_pack_router_v2.py"
spec = importlib.util.spec_from_file_location("router_v2", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def rec(text, path="ocr/page_text.jsonl"):
    return mod.EvidenceRecord(
        source_path=path,
        line_no=1,
        text=text,
        page_ids=tuple(sorted(set(m.group(0) for m in mod.PAGE_ID_RE.finditer(text)))),
        part_numbers=tuple(sorted(set(m.group(0) for m in mod.PART_RE.finditer(text)))),
        ata_numbers=tuple(sorted(set(m.group(0) for m in mod.ATA_RE.finditer(text)))),
        figure_refs=tuple(sorted(set(m.group(0) for m in mod.FIGURE_RE.finditer(text)))),
    )


def test_load_questions_accepts_wrapped_and_list(tmp_path):
    p = tmp_path / "questions.json"
    p.write_text(json.dumps({"questions": [{"question_id": "q01", "question": "Which page contains Figure 69?"}]}), encoding="utf-8")
    assert mod.load_questions(p)[0]["question_id"] == "q01"
    p.write_text(json.dumps([{"question": "What ATA number is visible?"}]), encoding="utf-8")
    assert mod.load_questions(p)[0]["question_id"] == "q01"


def test_classify_question_routes_specific_intents():
    assert mod.classify_question("I need an ATA number that starts with 2") == "ata_identifier"
    assert mod.classify_question("What revision is associated with the scanned document?") == "document_revision"
    assert mod.classify_question("Which pages mention warnings?") == "manual_keyword"
    assert mod.classify_question("Which page contains Figure 69?") == "figure_visual"
    assert mod.classify_question("What page has a blank table?") == "blank_layout"


def test_manual_warning_route_blocks_pipeline_warning_fields():
    good = rec("page_id: t_p_120_1176_p000477 text: WARNING: obey all safety precautions", "ocr/lines.jsonl")
    bad = rec("records[20].anchor_aware_warnings: missing source trace", "table/enrichment.json")
    assert mod.record_passes_route(good, "Which pages mention warnings?", "manual_keyword")
    assert not mod.record_passes_route(bad, "Which pages mention warnings?", "manual_keyword")


def test_ata_route_prefers_ata_pattern_over_revision_date():
    records = [
        rec("revision date: 10 April 2006 document T.-P. 120/1176", "metadata/doc.json"),
        rec("page_id: t_p_120_1176_p000005 title: ATA 25-21-00 Passenger Seat", "page_context_v2/context.jsonl"),
    ]
    route, evidence = mod.retrieve_evidence(records, "I need an ATA number that starts with 2. What page and document is that?", top_k=2)
    assert route == "ata_identifier"
    assert evidence
    assert "25-21-00" in evidence[0].text


def test_exact_phrase_route_does_not_return_unrelated_seat_parts():
    records = [
        rec("page_id: t_p_120_1176_p000316 69 - 120-50645-005 DOUBLE PASSENGER SEAT ASSY", "ocr/lines.jsonl"),
        rec("page_id: t_p_120_1176_p000020 PAPER TOWEL DISPENSER ASSY part 123-45678-001", "ocr/lines.jsonl"),
    ]
    route, evidence = mod.retrieve_evidence(records, "Which pages mention paper towel dispenser?", top_k=5)
    assert route == "exact_nomenclature_phrase"
    assert len(evidence) == 1
    assert "PAPER TOWEL" in evidence[0].text


def test_blank_answer_fallback_is_never_empty():
    answer, used = mod.normalize_answer("", question="Which pages contain ATA-style identifiers?", route="ata_identifier", evidence_count=0)
    assert used
    assert "Not found" in answer
    assert "Source-trace status" in answer
