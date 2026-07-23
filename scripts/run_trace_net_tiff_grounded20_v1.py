#!/usr/bin/env python3
"""Route-balanced 20-question live benchmark grounded in TRACE-Net's 509 TIFF pages."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

PART_RE = re.compile(r"\b\d{2,3}-\d{5}-\d{3}\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
PAGE_RE = re.compile(r"\bt_p_[a-z0-9_]+_p\d{6}\b", re.I)
PRIORITY_NOUNS = (
    "HINGE", "PIN", "LOCKING RING", "RING", "BRACKET", "LATCH", "COVER",
    "PANEL", "FITTING", "SCREW", "BOLT", "CLIP", "SEAT", "FASTENER",
    "RETAINER", "SPRING", "WASHER",
)


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--base-url", default="http://172.17.0.1:8131")
    p.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    p.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    p.add_argument("--output-dir", default="/data/trace_net_runs/cognitive_openwebui_h30_graph_synthesis_v1/tiff_grounded20_v1")
    p.add_argument("--request-timeout", type=float, default=240.0)
    p.add_argument("--bank-only", action="store_true")
    p.add_argument("--strict", action="store_true")
    return p.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("records", "cards", "items", "nodes", "graph_nodes"):
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
    return []


def norm_id(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def compact(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def route_of(card: Mapping[str, Any]) -> str:
    route = card.get("route")
    if isinstance(route, Mapping):
        return str(route.get("recommended_route_candidate") or route.get("best_route_candidate_before_review") or "")
    return str(route or card.get("recommended_route_candidate") or "")


def page_of(card: Mapping[str, Any]) -> str:
    return str(card.get("page_id") or card.get("source_page_id") or "")


def parts_of(card: Mapping[str, Any]) -> list[str]:
    blob = " ".join(
        compact(card.get(k), 8000)
        for k in ("important_parts", "v2_retrieval_summary", "v2_short_summary", "retrieval_profile", "ocr")
    )
    return list(dict.fromkeys(x.upper() for x in PART_RE.findall(blob)))


def v3_path(repo: Path) -> Path:
    """Locate either raw V3 cards or the deployed 509-page candidate bundle."""
    root = repo / "local_data/organization/trace_net"
    preferred = (
        root / "v3_page_intelligence/trace_net_v3_page_intelligence_cards_v1.json",
        root / "ocr_v2_v3_embedding_candidates/trace_net_ocr_v2_v3_embedding_candidates_v1.json",
    )
    for path in preferred:
        if path.exists():
            return path

    patterns = (
        "**/trace_net_v3_page_intelligence_cards_v1.json",
        "**/trace_net_ocr_v2_v3_embedding_candidates_v1.json",
    )
    for pattern in patterns:
        found = sorted(root.glob(pattern))
        if found:
            return found[0]

    raise FileNotFoundError(
        "Neither raw V3 cards nor the OCR/V2/V3 embedding candidate bundle was found"
    )


def v3_cards(payload: Any) -> list[dict[str, Any]]:
    """Return a uniform 509-page V3-card view from either artifact shape."""
    raw = records(payload)
    if not raw:
        return []

    # Raw V3 manifests already contain page-intelligence cards.
    if any(str(row.get("record_type") or "") == "v3_page_intelligence_card" for row in raw):
        return raw

    # The deployed Qdrant-source bundle contains three candidates per page. Keep
    # only its V3 candidate and adapt the safe metadata into the card fields used
    # by this benchmark. This bundle is the server artifact with 509 V3 pages.
    cards: list[dict[str, Any]] = []
    for row in raw:
        if str(row.get("candidate_type") or row.get("source_kind") or "") != "v3_page_intelligence":
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        embedding_text = str(
            row.get("embedding_text")
            or row.get("text")
            or row.get("chunk_text")
            or ""
        )
        cards.append({
            "record_type": "v3_page_intelligence_card_adapter",
            "page_id": row.get("page_id"),
            "page_number": row.get("page_number"),
            "source_path": row.get("source_path"),
            "route": {
                "recommended_route_candidate": metadata.get("recommended_route_candidate"),
                "review_required": bool(metadata.get("review_required")),
            },
            "retrieval_profile": {"text": embedding_text},
            "important_parts": PART_RE.findall(embedding_text),
            "ocr": {"sample_text": embedding_text},
            "v2_retrieval_summary": embedding_text,
            "proof_policy": {
                "guidance_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
        })
    return cards


def truth(repo: Path) -> dict[str, Any]:
    sys.path[:0] = [str(repo), str(repo / "scripts")]
    from tiff.trace_net_graph_query_helper_v1 import (  # type: ignore
        GraphIndex, collect_ata_codes, collect_part_nomenclature, extract_edges,
        extract_nodes, is_page_node, is_part_node, load_json_any, page_card,
        page_id, part_number,
    )

    np = repo / "local_data/organization/graph/graph_nodes.json"
    ep = repo / "local_data/organization/graph/graph_edges.json"
    vp = v3_path(repo)
    nodes = extract_nodes(load_json_any(np))
    edges = extract_edges(load_json_any(ep))
    graph = GraphIndex(nodes, edges)
    cards = v3_cards(load_json(vp))
    if not cards:
        raise ValueError(f"No V3 page-intelligence records found in {vp}")

    part_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in graph.nodes:
        if not is_part_node(node):
            continue
        pn = str(part_number(node) or "").upper()
        if not PART_RE.fullmatch(pn) or pn in seen:
            continue
        pages = [page_card(graph, p) for _e, p in graph.out_neighbors(node["node_id"], ["APPEARS_ON"]) if is_page_node(p)]
        pages = [p for p in pages if p.get("page_id")]
        if not pages:
            continue
        seen.add(pn)
        part_rows.append({
            "part": pn,
            "nomenclature": collect_part_nomenclature(graph, node),
            "pages": pages,
            "source_resolved": any(bool(p.get("source_resolved")) for p in pages),
        })
    part_rows.sort(key=lambda r: (not r["source_resolved"], not bool(r["nomenclature"]), r["part"]))

    ata_pages: dict[str, list[str]] = defaultdict(list)
    for node in graph.nodes:
        if is_page_node(node):
            for code in collect_ata_codes(graph, node):
                if ATA_RE.fullmatch(code):
                    ata_pages[code].append(page_id(node))

    return {
        "parts": part_rows,
        "cards": cards,
        "ata_pages": {k: sorted(set(v)) for k, v in ata_pages.items()},
        "paths": {"nodes": str(np), "edges": str(ep), "v3": str(vp)},
        "counts": {"graph_nodes": len(nodes), "graph_edges": len(edges), "v3_cards": len(cards), "parts_with_pages": len(part_rows)},
    }


def q(qid: str, category: str, question: str, route: str, ids=(), pages=(), terms=(), basis=None, negative=False) -> dict[str, Any]:
    return {
        "question_id": qid, "category": category, "question": question,
        "expected_route": route, "expected_identifiers": list(ids),
        "expected_pages": list(pages), "expected_terms": list(terms),
        "source_basis": basis or {}, "negative_control": negative,
    }


def build_bank(t: Mapping[str, Any]) -> list[dict[str, Any]]:
    parts = list(t["parts"])
    cards = list(t["cards"])
    used_parts: set[str] = set()
    used_pages: set[str] = set()
    bank: list[dict[str, Any]] = []

    def take_part(require_nomen=False) -> dict[str, Any]:
        for row in parts:
            if row["part"] in used_parts or not row["source_resolved"]:
                continue
            if require_nomen and not row["nomenclature"]:
                continue
            used_parts.add(row["part"])
            return row
        raise RuntimeError("Not enough grounded graph parts")

    # 3 exact parts.
    for i in range(1, 4):
        row = take_part(True); page = row["pages"][0]
        bank.append(q(f"q{i:02d}", "exact_part",
            f"Find part {row['part']} and explain its nomenclature, connected page, and source evidence.",
            "exact_identifier_lookup", [row["part"]], [page["page_id"]], row["nomenclature"], {"part": row["part"], "page": page}))

    # 3 partial modes.
    for i, mode in enumerate(("prefix", "contains", "suffix"), 4):
        row = take_part(); n = norm_id(row["part"])
        clue = n[:5] if mode == "prefix" else (n[3:8] if mode == "contains" else n[-3:])
        phrase = {"prefix": "starts with", "contains": "contains", "suffix": "ends with"}[mode]
        bank.append(q(f"q{i:02d}", f"partial_{mode}",
            f"I only remember that the part number {phrase} {clue}. Show matching candidates and source pages.",
            "guided_part_discovery", [row["part"]], [row["pages"][0]["page_id"]], basis={"part": row["part"], "clue": clue, "mode": mode}))

    # 3 actual nomenclature terms.
    noun_rows: list[tuple[str, dict[str, Any]]] = []
    seen_nouns: set[str] = set()
    for noun in PRIORITY_NOUNS:
        for row in parts:
            blob = " ".join(map(str, row["nomenclature"])).upper()
            if noun in blob and noun not in seen_nouns:
                noun_rows.append((noun, row)); seen_nouns.add(noun); break
    if len(noun_rows) < 3:
        for row in parts:
            for name in row["nomenclature"]:
                words = re.findall(r"[A-Z]{4,}", str(name).upper())
                for noun in words:
                    if noun not in {"ASSY", "ASSEMBLY", "SINGLE", "PASSENGER", "WITH"} and noun not in seen_nouns:
                        noun_rows.append((noun, row)); seen_nouns.add(noun); break
                if len(noun_rows) >= 3: break
            if len(noun_rows) >= 3: break
    if len(noun_rows) < 3:
        raise RuntimeError("Not enough nomenclature examples")
    for i, (noun, row) in enumerate(noun_rows[:3], 7):
        bank.append(q(f"q{i:02d}", "nomenclature",
            f"Find the {noun.lower()} in the document set. Show the best matching part candidates and connected source pages.",
            "nomenclature_function_search", [row["part"]], [row["pages"][0]["page_id"]], [noun], {"part": row["part"], "nomenclature": row["nomenclature"]}))

    # 2 ATA searches.
    atas = sorted(t["ata_pages"].items(), key=lambda x: (-len(x[1]), x[0]))[:2]
    if len(atas) < 2: raise RuntimeError("Not enough ATA codes")
    for i, (ata, pages) in enumerate(atas, 10):
        bank.append(q(f"q{i:02d}", "ata_system",
            f"Find the relevant parts and source pages in ATA {ata}. Summarize the strongest available evidence.",
            "ata_system_discovery", pages=pages[:5], terms=[ata], basis={"ata": ata, "pages": pages[:15]}))

    def choose_cards(predicate, count):
        selected = []
        for card in sorted(cards, key=lambda c: (page_of(c) in used_pages, not bool(parts_of(c)), page_of(c))):
            pid = page_of(card)
            if pid and predicate(card) and all(page_of(x) != pid for x in selected):
                selected.append(card)
                if len(selected) == count: break
        return selected

    # 2 table/IPL.
    table_cards = choose_cards(lambda c: route_of(c) in {"detailed_parts_list", "table_or_index"} or str(c.get("v2_role") or "").lower() in {"parts_list", "table", "index"}, 2)
    if len(table_cards) < 2: table_cards = choose_cards(lambda c: True, 2)
    for i, card in enumerate(table_cards, 12):
        pid = page_of(card); cp = parts_of(card)
        text = f"Search the IPL table for part {cp[0]} and show the matching row or source page." if cp else f"Search the IPL table on page {pid} and summarize the listed part information."
        bank.append(q(f"q{i:02d}", "table_ipl", text, "exact_table_ipl_lookup", cp[:1], [pid], basis={"page": pid, "route": route_of(card), "parts": cp, "source_path": card.get("source_path")})); used_pages.add(pid)

    # 2 visual.
    visual_cards = choose_cards(lambda c: route_of(c) in {"image_visual_diagram", "mixed_text_and_figure"} or str(c.get("v2_role") or "").lower() in {"figure", "diagram", "illustration"}, 2)
    if len(visual_cards) < 2: visual_cards = choose_cards(lambda c: True, 2)
    for i, card in enumerate(visual_cards, 14):
        pid = page_of(card); cp = parts_of(card)
        text = f"Show and explain the diagram for part {cp[0]} on page {pid}." if cp else f"Show and explain the component diagram on page {pid}."
        bank.append(q(f"q{i:02d}", "visual_figure", text, "visual_figure_callout_lookup", cp[:1], [pid], basis={"page": pid, "route": route_of(card), "source_path": card.get("source_path")})); used_pages.add(pid)

    # 1 procedure.
    proc = choose_cards(lambda c: route_of(c) == "procedure_or_description" or "procedure" in str(c.get("v2_role") or "").lower() or "procedure" in str(c.get("v2_subrole") or "").lower(), 1)
    if not proc: proc = choose_cards(lambda c: True, 1)
    card = proc[0]; pid = page_of(card)
    bank.append(q("q16", "procedure", f"What procedure or task is described on page {pid}? Give only steps supported by the source and note any limits.", "procedure_task_lookup", pages=[pid], basis={"page": pid, "route": route_of(card), "summary": card.get("v2_retrieval_summary"), "source_path": card.get("source_path")}))

    # 1 OCR recovery using a real OCR clue but no page-id atom.
    ocr_cards = [c for c in cards if len(compact((c.get("ocr") or {}).get("sample_text"), 1000)) >= 25]
    ocr_cards.sort(key=lambda c: (not bool((c.get("route") or {}).get("review_required")), page_of(c)))
    if not ocr_cards: raise RuntimeError("No OCR card")
    card = ocr_cards[0]; sample = compact((card.get("ocr") or {}).get("sample_text"), 1000); clue = " ".join(sample.split()[:8])
    bank.append(q("q17", "ocr_recovery", f"Recover the text from the blurry scanned page containing this OCR clue: '{clue}'. Cross-check the scan and report uncertainty.", "ocr_scan_recovery", pages=[page_of(card)], terms=[clue], basis={"page": page_of(card), "clue": clue, "source_path": card.get("source_path")}))

    # 1 graph relationship.
    row = next(r for r in parts if r["nomenclature"] and r["source_resolved"]); page = row["pages"][0]
    bank.append(q("q18", "graph_relationship", f"What assembly or nomenclature is connected to part {row['part']}, and which source page contains it?", "graph_relationship_reasoning", [row["part"]], [page["page_id"]], row["nomenclature"], {"part": row["part"], "page": page}))

    # 2 negative controls.
    bank.append(q("q19", "negative_part", "Find part 999-99999-999 and show its source page and nomenclature.", "exact_identifier_lookup", ["999-99999-999"], negative=True, basis={"reason": "nonexistent part"}))
    bank.append(q("q20", "negative_page", "Open page t_p_120_1176_p999999 and explain what it contains.", "document_page_navigation", pages=["t_p_120_1176_p999999"], negative=True, basis={"reason": "nonexistent page"}))
    assert len(bank) == 20
    return bank


def call(base: str, key: str, model: str, question: str, timeout: float) -> tuple[int, dict[str, Any], str]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": question}], "temperature": 0, "stream": False}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode("utf-8", "replace")), ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try: payload = json.loads(raw)
        except Exception: payload = {"error": raw}
        return exc.code, payload, str(exc)
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)}, f"{type(exc).__name__}: {exc}"


def answer(payload: Mapping[str, Any]) -> str:
    try: return str(payload["choices"][0]["message"]["content"])
    except Exception: return ""


def page_ids(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str): out.update(x.lower() for x in PAGE_RE.findall(value))
    elif isinstance(value, Mapping):
        for k, v in value.items():
            if k in {"page_id", "source_page_id", "document_page_id"} and isinstance(v, str): out.add(v.lower())
            out.update(page_ids(v))
    elif isinstance(value, list):
        for x in value: out.update(page_ids(x))
    return out


def evaluate(item: Mapping[str, Any], payload: Mapping[str, Any], status: int, ms: float, error: str) -> dict[str, Any]:
    text = answer(payload); trace = payload.get("trace_net") if isinstance(payload.get("trace_net"), Mapping) else {}
    env = trace.get("evidence_envelope") if isinstance(trace.get("evidence_envelope"), Mapping) else {}
    candidates = [str(r.get("candidate_value") or r.get("part_number") or "") for r in env.get("candidate_evidence") or [] if isinstance(r, Mapping)]
    norms = [norm_id(x) for x in candidates if norm_id(x)]
    expected_ids = {norm_id(x) for x in item["expected_identifiers"]}
    recovered_pages = page_ids(env) | page_ids(text)
    expected_pages = {x.lower() for x in item["expected_pages"]}
    validation = trace.get("post_answer_validation") if isinstance(trace.get("post_answer_validation"), Mapping) else {}
    synthesis = trace.get("evidence_synthesis") if isinstance(trace.get("evidence_synthesis"), Mapping) else {}
    mode = trace.get("answer_mode") if isinstance(trace.get("answer_mode"), Mapping) else {}
    timing = trace.get("timing") if isinstance(trace.get("timing"), Mapping) else {}
    used = list(env.get("retrieval_tunnels_used") or trace.get("retrieval_tunnels_used") or [])
    source_resolved = any(bool(r.get("source_resolved")) for r in env.get("candidate_evidence") or [] if isinstance(r, Mapping)) or bool(env.get("source_resolution"))
    negative_fabricated = bool(item["negative_control"] and (expected_ids & set(norms)))
    return {
        **{k: item[k] for k in ("question_id", "category", "question", "expected_route", "negative_control", "source_basis")},
        "actual_route": trace.get("route"), "route_match": trace.get("route") == item["expected_route"],
        "http_status": status, "transport_error": error, "nonempty_answer": bool(text.strip()), "latency_ms": round(ms, 3), "over_180_seconds": ms >= 180000,
        "quality_status": trace.get("quality_status"), "writer_mode": trace.get("writer_mode"), "answer_mode": mode.get("mode"),
        "gemma_called": bool(timing.get("gemma_called")), "gemma_status": trace.get("gemma_status"),
        "synthesis_attempted": synthesis.get("attempted"), "synthesis_written": synthesis.get("written"),
        "post_validation_accepted": validation.get("accepted"), "post_validation_failures": list(validation.get("failures") or []),
        "unknown_citation_id": "unknown_citation_id" in (validation.get("failures") or []),
        "candidate_count": len(candidates), "candidate_values": candidates, "duplicate_candidate_count": len(norms) - len(set(norms)),
        "expected_identifier_recovered": bool(expected_ids & set(norms)) or any(x and x in norm_id(text) for x in expected_ids),
        "expected_page_recovered": bool(expected_pages & recovered_pages) if expected_pages else False,
        "recovered_page_ids": sorted(recovered_pages), "source_resolved": source_resolved,
        "retrieval_tunnels_used": used, "negative_control_fabricated": negative_fabricated, "answer": text,
    }


def summarize(rows: list[dict[str, Any]], t: Mapping[str, Any]) -> dict[str, Any]:
    positives = [r for r in rows if not r["negative_control"]]; negatives = [r for r in rows if r["negative_control"]]
    failures = Counter(f for r in rows for f in r["post_validation_failures"])
    hard = []
    if sum(r["http_status"] == 200 for r in rows) != 20: hard.append("not_all_http_200")
    if sum(r["nonempty_answer"] for r in rows) != 20: hard.append("empty_answers")
    if any(r["duplicate_candidate_count"] for r in rows): hard.append("duplicate_candidates")
    if any(r["negative_control_fabricated"] for r in negatives): hard.append("negative_fabrication")
    if any(r["over_180_seconds"] for r in rows): hard.append("over_180_seconds")
    return {
        "quality_status": "PASS" if not hard else "WARN", "hard_failures": hard,
        "question_count": 20, "artifact_counts": t["counts"], "artifact_paths": t["paths"],
        "http_200_count": sum(r["http_status"] == 200 for r in rows), "nonempty_answer_count": sum(r["nonempty_answer"] for r in rows),
        "route_match_count": sum(r["route_match"] for r in rows),
        "expected_identifier_recovered_count": sum(r["expected_identifier_recovered"] for r in positives),
        "expected_page_recovered_count": sum(r["expected_page_recovered"] for r in positives), "source_resolved_count": sum(r["source_resolved"] for r in positives),
        "gemma_called_count": sum(r["gemma_called"] for r in rows), "synthesis_attempted_count": sum(bool(r["synthesis_attempted"]) for r in rows),
        "synthesis_written_count": sum(bool(r["synthesis_written"]) for r in rows), "post_validation_accepted_count": sum(bool(r["post_validation_accepted"]) for r in rows),
        "unknown_citation_id_count": sum(r["unknown_citation_id"] for r in rows), "post_validation_failure_counts": dict(failures),
        "duplicate_candidate_total": sum(r["duplicate_candidate_count"] for r in rows), "negative_control_fabricated_count": sum(r["negative_control_fabricated"] for r in negatives),
        "over_180_seconds_count": sum(r["over_180_seconds"] for r in rows),
        "average_latency_ms": round(sum(r["latency_ms"] for r in rows) / 20, 3), "maximum_latency_ms": max(r["latency_ms"] for r in rows),
        "route_counts": dict(Counter(str(r["actual_route"]) for r in rows)),
    }


def report(path: Path, s: Mapping[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = ["# TRACE-Net TIFF-grounded 20-question benchmark", "", f"Status: **{s['quality_status']}**", "",
             f"HTTP 200: {s['http_200_count']}/20  ", f"Route matches: {s['route_match_count']}/20  ",
             f"Expected identifiers recovered: {s['expected_identifier_recovered_count']}/18 positives  ",
             f"Expected pages recovered: {s['expected_page_recovered_count']}/18 positives  ",
             f"Post-validation accepted: {s['post_validation_accepted_count']}/20  ",
             f"unknown_citation_id: {s['unknown_citation_id_count']}  ", f"Negative fabrications: {s['negative_control_fabricated_count']}/2  ",
             f"Average latency: {s['average_latency_ms']/1000:.1f}s  ", f"Maximum latency: {s['maximum_latency_ms']/1000:.1f}s", "",
             "| ID | Category | Expected → Actual | HTTP | Entity | Page | Source | Validation | Latency |", "|---|---|---|---:|---:|---:|---:|---|---:|"]
    for r in rows:
        vf = "✓" if r["post_validation_accepted"] else (",".join(r["post_validation_failures"]) or "—")
        lines.append(f"| {r['question_id']} | {r['category']} | {r['expected_route']} → {r['actual_route']} | {r['http_status']} | {'✓' if r['expected_identifier_recovered'] else '—'} | {'✓' if r['expected_page_recovered'] else '—'} | {'✓' if r['source_resolved'] else '—'} | {vf} | {r['latency_ms']/1000:.1f}s |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    a = args(); repo = Path(a.repo_root).resolve(); out = Path(a.output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    t = truth(repo); print("artifact_counts=", json.dumps(t["counts"], indent=2))
    if t["counts"]["v3_cards"] != 509: print(f"WARNING expected 509 V3 cards, found {t['counts']['v3_cards']}")
    bank = build_bank(t); (out / "question_bank.json").write_text(json.dumps({"artifact_counts": t["counts"], "questions": bank}, indent=2), encoding="utf-8")
    print("question_bank=", out / "question_bank.json")
    if a.bank_only: return 0
    rows = []
    for i, item in enumerate(bank, 1):
        print("=" * 100); print(f"[{i:02d}/20] {item['question_id']} {item['category']}"); print(item["question"])
        start = time.perf_counter(); status, payload, error = call(a.base_url, a.api_key, a.model, item["question"], a.request_timeout); ms = (time.perf_counter() - start) * 1000
        row = evaluate(item, payload, status, ms, error); rows.append(row)
        (out / f"{i:02d}_{item['question_id']}_{item['category']}.json").write_text(json.dumps({"question": item, "evaluation": row, "raw_response": payload}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"http={status} route={row['actual_route']} expected={row['expected_route']} latency={ms/1000:.1f}s candidates={row['candidate_count']} page={row['expected_page_recovered']} validation={row['post_validation_accepted']} failures={row['post_validation_failures']}")
        print("answer:", " ".join(row["answer"].split())[:450] or "<EMPTY>")
    s = summarize(rows, t); (out / "summary.json").write_text(json.dumps({"summary": s, "records": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["question_id", "category", "expected_route", "actual_route", "route_match", "http_status", "latency_ms", "expected_identifier_recovered", "expected_page_recovered", "source_resolved", "gemma_called", "synthesis_written", "post_validation_accepted", "unknown_citation_id", "duplicate_candidate_count", "negative_control_fabricated", "post_validation_failures", "question"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows:
            x = {k: r.get(k) for k in fields}; x["post_validation_failures"] = json.dumps(x["post_validation_failures"]); w.writerow(x)
    report(out / "report.md", s, rows)
    print("=" * 100); print(json.dumps(s, indent=2)); print("report=", out / "report.md"); print("summary=", out / "summary.json")
    return 1 if a.strict and s["hard_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
