import json
from pathlib import Path

import sys
import types
import re

_grounded_stub = types.ModuleType("scripts.run_trace_net_tiff_grounded20_v1")
_grounded_stub.answer = lambda payload: str((((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""))
def _stub_pages(value):
    text = str(value)
    return {match.lower() for match in re.findall(r"t_p_[a-z0-9_]+_p\d{6}", text, re.I)}
_grounded_stub.evidence_page_ids = _stub_pages
_grounded_stub.truth = lambda repo: {}
_grounded_stub.call = lambda *args, **kwargs: (200, {}, "")
sys.modules.setdefault("scripts.run_trace_net_tiff_grounded20_v1", _grounded_stub)

from scripts.check_trace_net_h30_grounded100_v1 import inspect_run
from scripts.run_trace_net_h30_grounded100_v1 import summarize_records
from scripts.trace_net_h30_phase5_question_bank_v1 import bank_document, build_phase5_bank


def synthetic_truth():
    nouns = ["Pin Attach", "Ring Locking", "Cover Latch", "Panel Support", "Bracket", "Fitting", "Screw", "Bolt", "Clip", "Seat", "Fastener", "Retainer", "Spring", "Washer", "Armrest", "Support", "Hinge", "Table", "Leg"]
    parts = []
    for index in range(1, 70):
        part = f"120-{20000 + index:05d}-{index % 90 + 1:03d}"
        parts.append({"part": part, "nomenclature": [nouns[(index - 1) % len(nouns)]], "pages": [{"page_id": f"t_p_120_1176_p{index:06d}", "source_resolved": True}, {"page_id": f"t_p_120_1176_p{index + 100:06d}", "source_resolved": True}], "source_resolved": True})
    routes = ["detailed_parts_list", "table_or_index", "image_visual_diagram", "mixed_text_and_figure", "procedure_or_description", "normal_text"]
    cards = []
    for index in range(1, 90):
        page_id = f"t_p_120_1176_p{index:06d}"
        part = parts[(index - 1) % len(parts)]["part"]
        text = f"Unique OCR token BLOCK{index:04d} ROW{index:04d} {part} Figure {index}. Warning caution note. Procedure remove install adjust. Illustrated parts list table item. Manufacturer identifier MS{16000 + index}-{100 + index}."
        cards.append({"page_id": page_id, "source_path": f"source_{index}.tif", "route": {"recommended_route_candidate": routes[(index - 1) % len(routes)]}, "important_parts": [part], "v2_retrieval_summary": text, "ocr": {"sample_text": text}})
    ata_pages = {f"{20 + index:02d}-{10 + index:02d}-00": [f"t_p_120_1176_p{index:06d}"] for index in range(1, 15)}
    return {"parts": parts, "cards": cards, "ata_pages": ata_pages, "counts": {"graph_nodes": 100, "graph_edges": 200, "v3_cards": len(cards), "parts_with_pages": len(parts)}, "paths": {"nodes": "nodes.json", "edges": "edges.json", "v3": "v3.json"}}


def contract(bank):
    category_counts = {}
    for item in bank:
        category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1
    return {
        "contract_id": "trace_net_h30_phase5_grounded100_contract_v1",
        "expected_question_count": 100,
        "category_counts": category_counts,
        "thresholds": {
            "http_200_rate": 1.0,
            "nonempty_answer_rate": 1.0,
            "post_validation_accept_rate": 1.0,
            "public_contract_rate": 1.0,
            "route_match_rate": 0.9,
            "identifier_recovery_rate": 0.75,
            "page_recovery_rate": 0.7,
            "maximum_latency_ms": 180000,
            "maximum_constrained_calls_per_record": 1,
            "minimum_constrained_writer_accepted": 1,
            "maximum_unknown_citations": 0,
            "maximum_negative_fabrications": 0,
            "maximum_duplicate_candidates": 0,
            "maximum_public_internal_leaks": 0,
            "maximum_public_output_anomalies": 0,
            "maximum_unsafe_authority_assertions": 0,
            "maximum_required_citation_missing": 0,
            "maximum_record_hard_failures": 0
        }
    }


def passing_evaluation(item):
    return {
        "question_id": item["question_id"],
        "ordinal": item["ordinal"],
        "category": item["category"],
        "expected_route": item["expected_route"],
        "actual_route": item["expected_route"],
        "route_match": True,
        "http_status": 200,
        "latency_ms": 1000.0,
        "nonempty_answer": True,
        "post_validation_accepted": True,
        "unknown_citation_id": False,
        "public_contract_ok": True,
        "public_leaks": [],
        "public_output_anomalies": [],
        "required_citation_missing": False,
        "duplicate_candidate_count": 0,
        "identifier_question": bool(item["expected_identifiers"]) and not item["negative_control"],
        "page_question": bool(item["expected_pages"]) and not item["negative_control"],
        "expected_identifier_recovered": bool(item["expected_identifiers"]) and not item["negative_control"],
        "expected_page_recovered": bool(item["expected_pages"]) and not item["negative_control"],
        "negative_identifier_fabricated": False,
        "negative_page_fabricated": False,
        "unsafe_authority_assertion": False,
        "constrained_writer_call_count": 1 if item["expected_route"] in {"exact_identifier_lookup", "ata_system_discovery", "exact_table_ipl_lookup"} and not item["negative_control"] else 0,
        "constrained_writer_accepted": item["question_id"] == "q001",
        "constrained_writer_fallback": False,
        "hard_failures": [],
        "passed_hard_gates": True,
    }


def write_passing_run(run_dir: Path):
    truth = synthetic_truth()
    bank = build_phase5_bank(truth)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "question_bank.json").write_text(json.dumps(bank_document(bank, truth), indent=2), encoding="utf-8")
    records = []
    for item in bank:
        evaluation = passing_evaluation(item)
        records.append(evaluation)
        path = run_dir / f"{item['ordinal']:03d}_{item['question_id']}_{item['category']}.json"
        path.write_text(json.dumps({"question": item, "evaluation": evaluation, "raw_response": {}}), encoding="utf-8")
    summary = summarize_records(
        records, selected_count=100, full_bank_count=100,
        category_counts_expected=contract(bank)["category_counts"],
    )
    (run_dir / "summary.json").write_text(json.dumps({"summary": summary, "records": records}), encoding="utf-8")
    return bank


def test_checker_accepts_complete_safe_run(tmp_path):
    bank = write_passing_run(tmp_path)
    report = inspect_run(tmp_path, contract(bank))
    assert report["quality_status"] == "PASS", report
    assert report["record_count"] == 100


def test_checker_rejects_missing_record(tmp_path):
    bank = write_passing_run(tmp_path)
    next(tmp_path.glob("100_q100_*.json")).unlink()
    report = inspect_run(tmp_path, contract(bank))
    assert report["quality_status"] == "FAIL"
    assert any(value.startswith("record_file_count") for value in report["failures"])

# TRACE_NET_H30_PHASE5_CALIBRATED_CHECKER_V1
def test_checker_rejects_public_model_meta_anomaly(tmp_path):
    bank = write_passing_run(tmp_path)
    path = next(tmp_path.glob("001_q001_*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evaluation"]["public_output_anomalies"] = ["the user's prompt contains an error"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = inspect_run(tmp_path, contract(bank))
    assert report["quality_status"] == "FAIL"
    assert any("public_output_anomaly_count" in value for value in report["failures"])
