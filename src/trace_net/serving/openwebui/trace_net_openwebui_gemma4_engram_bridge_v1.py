from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


MODULE = "trace_net_openwebui_gemma4_engram_bridge_v1"
VERSION = "v1"
MODEL_ID = "trace-net-gemma4-engram-e2e-v1"
DEFAULT_QUESTION = "Find part number 120-50645-005. Give the nomenclature if available and cite the source."
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")


@dataclass
class EvidenceCard:
    label: str
    route: str
    source_artifact: str
    page_id: str
    page_number: str
    part_number: str
    nomenclature: str
    field: str
    value: str
    text: str
    source_trace_ready: bool = True
    citation_ready: bool = True
    proof_role: str = "proof_context"


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _safe_read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def artifact_route(path: str | Path, rec: Mapping[str, Any]) -> str:
    s = str(path).replace("\\", "/").lower()
    blob = json.dumps(rec, ensure_ascii=False).lower()
    route = _norm(rec.get("route") or rec.get("primary_route") or rec.get("selected_route")).lower()
    if route:
        return route
    if "table_exact_search" in s or "exact_search" in s:
        return "exact"
    if "table_route" in s or "table_" in s:
        return "table"
    if "raw_ocr" in s or "ocr_" in s:
        return "ocr"
    if "image_visual" in s or "visual" in s:
        return "visual"
    if "v2_summary" in s or "summary" in s:
        return "summary_guidance"
    if "engram" in s:
        return "engram_guidance"
    if "ocr" in blob:
        return "ocr"
    return "artifact"


def extract_page_id(rec: Mapping[str, Any]) -> str:
    for key in [
        "page_id", "source_page_id", "source_trace_page_id", "trace_page_id",
        "image_page_id", "manual_page_id", "page_key",
    ]:
        v = _norm(rec.get(key))
        if v and "metadata" not in v.lower():
            return v
    blob = json.dumps(rec, ensure_ascii=False)
    m = re.search(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b", blob)
    if m:
        return m.group(0)
    m = re.search(r"\bp\d{6}\b", blob)
    if m:
        return m.group(0)
    return ""


def extract_page_number(page_id: str, rec: Mapping[str, Any]) -> str:
    for key in ["page_number", "page", "source_page", "manual_page"]:
        v = _norm(rec.get(key))
        if re.fullmatch(r"\d{1,6}", v):
            return str(int(v))
    m = re.search(r"p0*([0-9]{1,6})\b", page_id)
    if m:
        return str(int(m.group(1)))
    return ""


def extract_part_number(rec: Mapping[str, Any]) -> str:
    for key in [
        "part_number", "covered_part_number", "ipl_part_number", "matched_part_number",
        "query_part_number", "part_no", "pn",
    ]:
        v = _norm(rec.get(key))
        m = PART_RE.search(v)
        if m:
            return m.group(0)
    blob = json.dumps(rec, ensure_ascii=False)
    m = PART_RE.search(blob)
    return m.group(0) if m else ""


def extract_nomenclature(rec: Mapping[str, Any], part_number: str = "") -> str:
    keys = [
        "nomenclature", "part_name", "description", "item_name", "name",
        "ocr_nomenclature", "line_nomenclature",
    ]
    for key in keys:
        v = _norm(rec.get(key))
        if v and len(v) > 2 and not v.lower().startswith(("trace_net_", "source_", "quality_")):
            if PART_RE.fullmatch(v):
                continue
            return v[:240]

    # Try to infer from OCR line text: "120-50645-005 DOUBLE PASSENGER SEAT ASSY ..."
    for key in ["line_text", "ocr_line_text", "text", "raw_text", "preview", "value"]:
        v = _norm(rec.get(key))
        if not v:
            continue
        if part_number and part_number in v:
            tail = v.split(part_number, 1)[-1]
            tail = re.split(r"\.{3,}| {4,}| VS\d+| REF\b", tail, flags=re.I)[0]
            tail = re.sub(r"^[\s|:\-]+", "", tail).strip()
            if 3 <= len(tail) <= 120:
                return tail
    return ""


def compact_text_from_record(rec: Mapping[str, Any], max_chars: int = 700) -> Tuple[str, str, str]:
    useful_keys = [
        "line_text", "ocr_line_text", "text", "raw_text", "preview", "answer_preview",
        "value", "field_value", "covered_part_number", "nomenclature", "description",
        "figure", "figure_number", "callout", "page_id", "source_trace", "source_trace_id",
    ]
    parts = []
    field = ""
    value = ""
    for key in useful_keys:
        if key in rec:
            v = _norm(rec.get(key))
            if v:
                parts.append(f"{key}={v}")
                if not field:
                    field, value = key, v
    if not parts:
        blob = json.dumps(rec, ensure_ascii=False)
        parts = [blob]
    text = " | ".join(parts)
    return text[:max_chars], field, value[:260]


def load_engram_guidance(paths: List[str | Path], max_rules: int = 18) -> str:
    seed = [
        "Vision summaries, page summaries, Engram, and planner guidance are guidance only; they are not proof.",
        "Factual source claims require proof_context citations from OCR, table, exact-search, graph, or source-trace evidence.",
        "If a part lookup is not found in proof_context, say not source-trace-ready rather than guessing.",
        "Do not claim interchangeability, fit, effectivity, replacement approval, or installation safety unless explicit authority is cited.",
        "Use cautious engineering sections: Answer, Evidence, Engineering confidence, Limits.",
        "For page/random-page questions, describe only what the selected evidence supports and list uncertainty.",
    ]
    rules: List[str] = []
    for path in paths:
        if not Path(path).exists():
            continue
        data = _safe_read_json(path)
        if data is None:
            continue
        for rec in iter_dicts(data):
            rule = _norm(rec.get("rule") or rec.get("guidance") or rec.get("text") or rec.get("content"))
            layer = _norm(rec.get("memory_layer") or rec.get("layer") or rec.get("memory_type"))
            proof_role = _norm(rec.get("proof_role"))
            if rule and len(rule) > 20:
                prefix = f"{layer}: " if layer else ""
                suffix = f" [{proof_role}]" if proof_role else ""
                rules.append(prefix + rule + suffix)

    out: List[str] = []
    seen = set()
    for item in seed + rules:
        k = item.lower()
        if k not in seen:
            seen.add(k)
            out.append(f"- {item}")
        if len(out) >= max_rules:
            break
    return "\n".join(out)


def default_artifact_paths() -> List[str]:
    return [
        "local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json",
        "local_data/organization/trace_net/table_route_evidence_packager/trace_net_table_route_evidence_packager_v1.json",
        "local_data/organization/trace_net/image_visual_evidence_nomenclature_merger_v1/trace_net_image_visual_evidence_pack_with_nomenclature_v1.json",
        "local_data/organization/trace_net/raw_ocr_nomenclature_window_extractor_v1/trace_net_raw_ocr_nomenclature_window_extractor_v1.json",
        "local_data/organization/trace_net/v2_summary_guidance_index_v1/trace_net_v2_summary_guidance_index_v1.json",
    ]


def default_engram_paths() -> List[str]:
    return [
        "local_data/organization/trace_net/engineering_engram_memory_layers_v1/trace_net_engineering_engram_memory_layers_v1.json",
        "local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json",
        "local_data/organization/trace_net/engineering_engram_answer_runner_retrieval_bridge_v1/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.json",
    ]


def build_evidence_index(paths: List[str | Path], max_records_per_artifact: int = 2500) -> List[EvidenceCard]:
    cards: List[EvidenceCard] = []
    counters: Dict[str, int] = {}

    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        data = _safe_read_json(path)
        if data is None:
            continue

        seen_text_hashes = set()
        count_for_path = 0
        for rec in iter_dicts(data):
            if count_for_path >= max_records_per_artifact:
                break

            page_id = extract_page_id(rec)
            page_number = extract_page_number(page_id, rec)
            part = extract_part_number(rec)
            text, field, value = compact_text_from_record(rec)
            nom = extract_nomenclature(rec, part)
            route = artifact_route(path, rec)

            # Keep useful records only.
            if not (page_id or part or nom or text):
                continue
            if route == "engram_guidance":
                continue

            hash_key = hashlib.sha1((route + "|" + page_id + "|" + part + "|" + text[:250]).encode("utf-8", errors="ignore")).hexdigest()
            if hash_key in seen_text_hashes:
                continue
            seen_text_hashes.add(hash_key)

            prefix = {
                "exact": "E",
                "table": "T",
                "ocr": "O",
                "visual": "V",
                "summary_guidance": "S",
            }.get(route, "A")
            counters[prefix] = counters.get(prefix, 0) + 1
            label = f"{prefix}{counters[prefix]}"

            cards.append(EvidenceCard(
                label=label,
                route=route,
                source_artifact=str(path),
                page_id=page_id,
                page_number=page_number,
                part_number=part,
                nomenclature=nom,
                field=field,
                value=value,
                text=text,
                source_trace_ready=route != "summary_guidance",
                citation_ready=route != "summary_guidance",
                proof_role="guidance_only" if route == "summary_guidance" else "proof_context",
            ))
            count_for_path += 1

    return cards


def query_kind(query: str) -> str:
    q = query.lower()
    if PART_RE.search(query):
        return "part_lookup"
    if re.search(r"\brandom\b", q) and re.search(r"\bpage|record|figure\b", q):
        return "random_page"
    if re.search(r"\bpage\s+\d{1,6}\b", q):
        return "page_lookup"
    if "nomenclature" in q:
        return "nomenclature_lookup"
    if "quiz" in q:
        return "quiz_generation"
    if "summarize" in q or "summary" in q:
        return "summary"
    return "general"


def page_number_from_query(query: str) -> str:
    m = re.search(r"\bpage\s+(\d{1,6})\b", query.lower())
    return str(int(m.group(1))) if m else ""


def score_card(card: EvidenceCard, query: str, kind: str) -> int:
    q = query.lower()
    text = " ".join([
        card.page_id, card.page_number, card.part_number, card.nomenclature,
        card.text, card.route,
    ]).lower()
    score = 0

    if kind == "part_lookup":
        part = PART_RE.search(query)
        if part and part.group(0) == card.part_number:
            score += 1000
        if part and part.group(0) in text:
            score += 500
        if card.route == "exact":
            score += 70
        if card.route == "ocr":
            score += 60
        if card.route == "table":
            score += 50
        if card.route == "visual":
            score += 40

    elif kind == "page_lookup":
        pn = page_number_from_query(query)
        if pn and card.page_number == pn:
            score += 1000
        if pn and f"p{int(pn):06d}" in card.page_id:
            score += 1000
        if card.part_number:
            score += 30

    elif kind == "random_page":
        if card.page_id:
            score += 50
        if card.part_number:
            score += 20
        if card.nomenclature:
            score += 20
        if card.route in ("ocr", "visual", "table", "exact"):
            score += 10

    else:
        terms = [t for t in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,}", q) if t not in {"the", "and", "for", "with", "from", "what", "give"}]
        for term in terms:
            if term.lower() in text:
                score += 50
        if card.part_number:
            score += 5
        if card.nomenclature:
            score += 5

    if card.proof_role == "proof_context":
        score += 5
    return score


def choose_random_page_cards(cards: List[EvidenceCard], max_cards: int, seed_text: str) -> List[EvidenceCard]:
    pages: Dict[str, List[EvidenceCard]] = {}
    for c in cards:
        if not c.page_id:
            continue
        if c.proof_role != "proof_context":
            continue
        pages.setdefault(c.page_id, []).append(c)

    eligible = [pid for pid, cs in pages.items() if len(cs) >= 1]
    if not eligible:
        return []

    # Actually random by default, but seedable by question text so tests are stable if wanted.
    rnd = random.Random(time.time_ns() ^ int(hashlib.sha1(seed_text.encode()).hexdigest()[:8], 16))
    page_id = rnd.choice(eligible)
    page_cards = pages[page_id]
    page_cards = sorted(page_cards, key=lambda c: (0 if c.part_number else 1, 0 if c.nomenclature else 1, c.route))
    return page_cards[:max_cards]


def retrieve_evidence(cards: List[EvidenceCard], query: str, max_cards: int = 10) -> Tuple[str, List[EvidenceCard]]:
    kind = query_kind(query)

    if kind == "random_page":
        selected = choose_random_page_cards(cards, max_cards, query)
        return kind, selected

    scored = [(score_card(c, query, kind), c) for c in cards]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    selected: List[EvidenceCard] = []
    seen = set()
    for _, c in scored:
        key = (c.label, c.page_id, c.part_number, c.text[:120])
        if key in seen:
            continue
        seen.add(key)
        selected.append(c)
        if len(selected) >= max_cards:
            break

    return kind, selected


def evidence_block(cards: List[EvidenceCard]) -> str:
    lines = []
    for c in cards:
        lines.append(
            f"[{c.label}] route={c.route} page={c.page_id or c.page_number} "
            f"part={c.part_number or 'n/a'} nomenclature={c.nomenclature or 'n/a'} "
            f"field={c.field or 'n/a'} value={c.value or 'n/a'} "
            f"proof_role={c.proof_role} text={c.text[:600]}"
        )
    return "\n".join(lines)


def build_prompt(query: str, kind: str, cards: List[EvidenceCard], engram_guidance: str) -> str:
    if not cards:
        evidence = "NO SOURCE-TRACE-READY PROOF_CONTEXT CARDS WERE RETRIEVED."
    else:
        evidence = evidence_block(cards)

    return f"""
TRACE-NET GEMMA4 ENGRAM E2E ANSWER RUNNER

You are TRACE-Net's cautious engineering answer runner.
Use the Engram behavior guidance below, but remember: Engram is behavior guidance, not proof.

ENGRAM GUIDANCE:
{engram_guidance}

TASK_TYPE:
{kind}

USER_QUERY:
{query}

PROOF_CONTEXT / EVIDENCE CARDS:
{evidence}

ANSWER CONTRACT:
- Use sections: Answer, Evidence, Engineering confidence, Limits.
- Every factual source claim must cite one or more labels like [E1] [O2] [V3].
- If no proof_context was retrieved, say "not source-trace-ready" and do not invent an answer.
- V2/page summaries and Engram guidance may guide wording only; do not use them as proof.
- Do not claim interchangeability, effectivity, fit, replacement approval, or installation safety unless explicit authority appears in proof_context.
- Keep answer concise, normally under 900 words.
- For random/page queries, describe what the selected source-trace evidence supports.
- For part lookups, answer the exact part in the user query, not a different part.
""".strip()


def call_ollama(prompt: str, model: str, url: str, timeout: int = 240) -> Tuple[str, str]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.05, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip(), ""
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return "", f"HTTPError {exc.code}: {exc.reason}; body={body[:1000]}"
    except Exception as exc:
        return "", repr(exc)


def deterministic_answer(query: str, kind: str, cards: List[EvidenceCard]) -> str:
    if not cards:
        return (
            "Answer\n"
            "Not source-trace-ready. TRACE-Net did not retrieve source-trace-ready proof_context for this query.\n\n"
            "Evidence\n"
            "No proof_context cards were available.\n\n"
            "Engineering confidence\n"
            "Low.\n\n"
            "Limits\n"
            "No part identity, page content, interchangeability, effectivity, fit, replacement approval, or installation safety claim is proven."
        )

    if kind == "part_lookup":
        part = PART_RE.search(query)
        requested = part.group(0) if part else ""
        matching = [c for c in cards if requested and requested in (c.part_number + " " + c.text)]
        use = matching or cards
        cites = " ".join(f"[{c.label}]" for c in use[:4])
        nom = next((c.nomenclature for c in use if c.nomenclature), "")
        page = next((c.page_id or c.page_number for c in use if c.page_id or c.page_number), "")
        ans = f"Part {requested} was found in source-trace-ready evidence"
        if nom:
            ans += f" with nomenclature: {nom}"
        if page:
            ans += f" on page {page}"
        ans += f". {cites}"
    elif kind == "random_page":
        page = cards[0].page_id or cards[0].page_number
        cites = " ".join(f"[{c.label}]" for c in cards[:5])
        parts = sorted({c.part_number for c in cards if c.part_number})
        noms = sorted({c.nomenclature for c in cards if c.nomenclature})
        ans = f"Selected representative page/record: {page}. TRACE-Net can safely say this page has source-trace evidence"
        if parts:
            ans += f" for part numbers including {', '.join(parts[:5])}"
        if noms:
            ans += f" and nomenclature including {', '.join(noms[:3])}"
        ans += f". {cites}"
    elif kind == "page_lookup":
        page = cards[0].page_id or cards[0].page_number
        cites = " ".join(f"[{c.label}]" for c in cards[:5])
        parts = sorted({c.part_number for c in cards if c.part_number})
        ans = f"Page {page} has retrieved source-trace evidence"
        if parts:
            ans += f" involving part numbers including {', '.join(parts[:5])}"
        ans += f". {cites}"
    else:
        cites = " ".join(f"[{c.label}]" for c in cards[:5])
        ans = f"TRACE-Net retrieved source-trace evidence relevant to the query. {cites}"

    evidence_lines = []
    for c in cards[:6]:
        evidence_lines.append(f"- [{c.label}] route={c.route}, page={c.page_id or c.page_number}, part={c.part_number or 'n/a'}, nomenclature={c.nomenclature or 'n/a'}")

    return (
        "Answer\n"
        f"{ans}\n\n"
        "Evidence\n"
        + "\n".join(evidence_lines)
        + "\n\nEngineering confidence\n"
        "Medium/high for claims directly supported by cited evidence; lower for any unclear OCR/visual observations.\n\n"
        "Limits\n"
        "This does not prove interchangeability, effectivity, fit, replacement approval, or installation safety. Engram and summary guidance are not proof."
    )


def build_citations(cards: List[EvidenceCard]) -> List[Dict[str, Any]]:
    return [
        {
            "label": c.label,
            "route": c.route,
            "page": c.page_id or c.page_number,
            "field": c.field,
            "value": c.value,
            "part_number": c.part_number,
            "nomenclature": c.nomenclature,
            "source_artifact": c.source_artifact,
            "source_trace_ready": c.source_trace_ready,
            "citation_ready": c.citation_ready,
        }
        for c in cards
    ]


class BridgeState:
    def __init__(
        self,
        artifact_paths: List[str],
        engram_paths: List[str],
        ollama_model: str,
        ollama_url: str,
        max_evidence_cards: int,
        output_dir: str | Path,
    ) -> None:
        self.artifact_paths = artifact_paths
        self.engram_paths = engram_paths
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        self.max_evidence_cards = max_evidence_cards
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engram_guidance = load_engram_guidance(engram_paths)
        self.evidence_cards = build_evidence_index(artifact_paths)
        self.started_at = time.time()

    def answer(self, query: str) -> Dict[str, Any]:
        kind, cards = retrieve_evidence(self.evidence_cards, query, max_cards=self.max_evidence_cards)
        prompt = build_prompt(query, kind, cards, self.engram_guidance)
        answer, llm_error = call_ollama(prompt, self.ollama_model, self.ollama_url)
        fallback_used = False
        if not answer:
            fallback_used = True
            answer = deterministic_answer(query, kind, cards)

        result = {
            "answer": answer,
            "response": answer,
            "query": query,
            "task_type": kind,
            "model": self.ollama_model,
            "llm_error": llm_error,
            "fallback_used": fallback_used,
            "evidence_card_count": len(cards),
            "citations": build_citations(cards),
            "safety": {
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
            },
        }
        self.log_query(result)
        return result

    def log_query(self, result: Dict[str, Any]) -> None:
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            digest = hashlib.sha1((result.get("query") or "").encode("utf-8")).hexdigest()[:10]
            _write_json(self.output_dir / "query_logs" / f"{ts}_{digest}.json", result)
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "TraceNetGemma4EngramBridge/1.0"

    @property
    def state(self) -> BridgeState:
        return self.server.state  # type: ignore[attr-defined]

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._send_json({
                "status": "ok",
                "quality_status": "PASS",
                "module": MODULE,
                "version": VERSION,
                "model_id": MODEL_ID,
                "ollama_model": self.state.ollama_model,
                "evidence_card_count": len(self.state.evidence_cards),
                "engram_guidance_loaded": bool(self.state.engram_guidance),
                "uptime_seconds": round(time.time() - self.state.started_at, 1),
                "safety": {
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                    "write_attempt_count": 0,
                },
            })
            return
        if self.path.startswith("/v1/models"):
            self._send_json({
                "object": "list",
                "data": [
                    {
                        "id": MODEL_ID,
                        "object": "model",
                        "created": int(self.state.started_at),
                        "owned_by": "trace-net-local",
                    }
                ],
            })
            return
        self._send_json({"error": {"message": "not found", "type": "not_found"}}, status=404)

    def do_POST(self) -> None:
        data = self._read_json_body()

        if self.path.startswith("/api/trace-net/ask"):
            query = _norm(data.get("query") or data.get("question"))
            if not query:
                messages = data.get("messages") or []
                if messages:
                    query = _norm(messages[-1].get("content"))
            if not query:
                self._send_json({"error": {"message": "Missing query or user message", "type": "bad_request"}}, status=400)
                return
            self._send_json(self.state.answer(query))
            return

        if self.path.startswith("/v1/chat/completions"):
            messages = data.get("messages") or []
            query = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    query = _norm(msg.get("content"))
                    break
            if not query:
                query = _norm(data.get("query") or data.get("question"))
            if not query:
                self._send_json({"error": {"message": "Missing user message", "type": "bad_request"}}, status=400)
                return

            result = self.state.answer(query)
            self._send_json({
                "id": "chatcmpl-trace-net-gemma4-engram",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": MODEL_ID,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": result["answer"],
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "trace_net": {
                    "task_type": result["task_type"],
                    "fallback_used": result["fallback_used"],
                    "evidence_card_count": result["evidence_card_count"],
                    "citations": result["citations"],
                    "safety": result["safety"],
                },
            })
            return

        self._send_json({"error": {"message": "not found", "type": "not_found"}}, status=404)


def serve(
    host: str,
    port: int,
    artifact_paths: List[str],
    engram_paths: List[str],
    ollama_model: str,
    ollama_url: str,
    max_evidence_cards: int,
    output_dir: str,
) -> None:
    state = BridgeState(
        artifact_paths=artifact_paths,
        engram_paths=engram_paths,
        ollama_model=ollama_model,
        ollama_url=ollama_url,
        max_evidence_cards=max_evidence_cards,
        output_dir=output_dir,
    )
    server = ThreadingHTTPServer((host, port), Handler)
    server.state = state  # type: ignore[attr-defined]
    print(f"status=TRACE_NET_OPENWEBUI_GEMMA4_ENGRAM_BRIDGE_STARTED", flush=True)
    print(f"quality_status=PASS", flush=True)
    print(f"host={host}", flush=True)
    print(f"port={port}", flush=True)
    print(f"model_id={MODEL_ID}", flush=True)
    print(f"ollama_model={ollama_model}", flush=True)
    print(f"evidence_card_count={len(state.evidence_cards)}", flush=True)
    print(f"engram_guidance_loaded={bool(state.engram_guidance)}", flush=True)
    server.serve_forever()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net Open WebUI Gemma4+Engram bridge")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--ollama-model", default="gemma4:26b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--artifact", action="append", default=None, help="Artifact JSON path. Repeatable. Defaults to key TRACE-Net artifacts.")
    parser.add_argument("--engram", action="append", default=None, help="Engram JSON path. Repeatable. Defaults to key Engram artifacts.")
    parser.add_argument("--max-evidence-cards", type=int, default=10)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/openwebui_gemma4_engram_bridge_v1")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    serve(
        host=args.host,
        port=args.port,
        artifact_paths=args.artifact or default_artifact_paths(),
        engram_paths=args.engram or default_engram_paths(),
        ollama_model=args.ollama_model,
        ollama_url=args.ollama_url,
        max_evidence_cards=args.max_evidence_cards,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
