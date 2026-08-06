from __future__ import annotations

import argparse
import json
import re
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from tiff import trace_net_openwebui_gemma4_engram_bridge_v1 as v1


MODULE = "trace_net_openwebui_gemma4_engram_bridge_v2"
VERSION = "v2"
MODEL_ID = "trace-net-gemma4-engram-e2e-v2"

CORPUS_STATS_PATTERNS = [
    r"\bhow many pages\b",
    r"\bhow many source pages\b",
    r"\bhow many manual pages\b",
    r"\bwhat pages can\b",
    r"\bpages can you\b",
    r"\bpage count\b",
    r"\bcorpus size\b",
    r"\bmanual size\b",
]

METRIC_OR_METADATA_TERMS = [
    "can_answer_directly_count",
    "can_prove_claims_count",
    "quality_status",
    "quality_failures",
    "answer_permission_count",
    "write_attempt_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
]


def query_kind(query: str) -> str:
    q = query.lower()
    if any(re.search(pattern, q) for pattern in CORPUS_STATS_PATTERNS):
        return "corpus_stats"
    return v1.query_kind(query)


def iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    yield from v1.iter_dicts(obj)


def _read_json(path: str | Path) -> Any:
    return v1._safe_read_json(path)


def _norm(value: Any) -> str:
    return v1._norm(value)


def _is_metric_or_metadata_card(card: v1.EvidenceCard) -> bool:
    hay = " ".join([
        card.label,
        card.route,
        card.page_id,
        card.page_number,
        card.part_number,
        card.nomenclature,
        card.field,
        card.value,
        card.text,
    ]).lower()
    if any(term in hay for term in METRIC_OR_METADATA_TERMS):
        return True
    if not card.page_id and not card.page_number and not card.part_number:
        return True
    return False


def filter_evidence_cards(cards: List[v1.EvidenceCard]) -> List[v1.EvidenceCard]:
    """Remove metrics/summary counters from the evidence pool.

    V1 allowed corpus metric fields like can_answer_directly_count to become
    answer evidence. V2 prevents those from being selected for normal queries.
    """
    out: List[v1.EvidenceCard] = []
    seen = set()
    for card in cards:
        if _is_metric_or_metadata_card(card):
            continue
        key = (card.route, card.page_id, card.page_number, card.part_number, card.nomenclature, card.text[:180])
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
    return out


def page_sort_key(page_id: str) -> Tuple[int, str]:
    m = re.search(r"p0*([0-9]{1,6})\b", page_id)
    if m:
        return int(m.group(1)), page_id
    m = re.search(r"([0-9]{1,6})", page_id)
    if m:
        return int(m.group(1)), page_id
    return 999999, page_id


def collect_source_pages_from_artifacts(paths: List[str | Path]) -> Dict[str, Any]:
    pages: Dict[str, Dict[str, Any]] = {}
    source_artifacts: Set[str] = set()

    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        data = _read_json(path)
        if data is None:
            continue
        source_artifacts.add(str(path))
        for rec in iter_dicts(data):
            page_id = v1.extract_page_id(rec)
            if not page_id:
                continue
            if "metadata" in page_id.lower() or page_id.lower().startswith("source_p"):
                continue
            page_number = v1.extract_page_number(page_id, rec)
            item = pages.setdefault(page_id, {
                "page_id": page_id,
                "page_number": page_number,
                "source_artifact_count": 0,
                "record_count": 0,
            })
            if page_number and not item.get("page_number"):
                item["page_number"] = page_number
            item["record_count"] += 1
            item["source_artifact_count"] += 1

    sorted_pages = sorted(pages.values(), key=lambda r: page_sort_key(r["page_id"]))
    page_numbers = [int(p["page_number"]) for p in sorted_pages if str(p.get("page_number") or "").isdigit()]
    return {
        "source_page_count": len(sorted_pages),
        "first_page_id": sorted_pages[0]["page_id"] if sorted_pages else "",
        "last_page_id": sorted_pages[-1]["page_id"] if sorted_pages else "",
        "min_page_number": min(page_numbers) if page_numbers else None,
        "max_page_number": max(page_numbers) if page_numbers else None,
        "page_ids_sample_first": [p["page_id"] for p in sorted_pages[:5]],
        "page_ids_sample_last": [p["page_id"] for p in sorted_pages[-5:]],
        "source_artifacts": sorted(source_artifacts),
    }


def corpus_stats_answer(stats: Mapping[str, Any]) -> Dict[str, Any]:
    count = int(stats.get("source_page_count") or 0)
    first_page_id = stats.get("first_page_id") or ""
    last_page_id = stats.get("last_page_id") or ""
    min_page = stats.get("min_page_number")
    max_page = stats.get("max_page_number")
    first_sample = stats.get("page_ids_sample_first") or []
    last_sample = stats.get("page_ids_sample_last") or []

    answer = (
        "Answer\n"
        f"TRACE-Net currently has {count} source pages available in the local corpus/page artifacts. "
    )
    if min_page is not None and max_page is not None:
        answer += f"The page-number range represented is {min_page} through {max_page}. "
    if first_page_id and last_page_id:
        answer += f"The first observed page id is {first_page_id}, and the last observed page id is {last_page_id}. [M1]\n\n"
    else:
        answer += "[M1]\n\n"

    answer += (
        "Evidence\n"
        f"- [M1] Corpus/page artifact scan counted {count} unique source page IDs from TRACE-Net local artifacts.\n"
        f"- First sample: {', '.join(first_sample)}\n"
        f"- Last sample: {', '.join(last_sample)}\n\n"
        "Engineering confidence\n"
        "High for the local artifact page count. This is a corpus-coverage answer, not a manual technical claim.\n\n"
        "Limits\n"
        "The count means TRACE-Net can route/retrieve over these page artifacts. It does not mean every page has equally rich OCR, table, visual, or part-number proof. "
        "It also does not prove interchangeability, effectivity, fit, replacement approval, or installation safety."
    )
    return {
        "answer": answer,
        "response": answer,
        "query": "",
        "task_type": "corpus_stats",
        "model": "deterministic_corpus_stats",
        "llm_error": "",
        "fallback_used": False,
        "evidence_card_count": 1,
        "citations": [
            {
                "label": "M1",
                "route": "corpus_manifest",
                "page": "",
                "field": "source_page_count",
                "value": count,
                "source_artifact": "TRACE-Net local artifact scan",
                "source_trace_ready": True,
                "citation_ready": True,
            }
        ],
        "safety": {
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }


class BridgeStateV2(v1.BridgeState):
    def __init__(
        self,
        artifact_paths: List[str],
        engram_paths: List[str],
        ollama_model: str,
        ollama_url: str,
        max_evidence_cards: int,
        output_dir: str | Path,
        llm_policy: str = "auto",
        fast_task_types: Optional[List[str]] = None,
    ) -> None:
        self.llm_policy = llm_policy
        self.fast_task_types = set(fast_task_types or ["corpus_stats"])
        super().__init__(
            artifact_paths=artifact_paths,
            engram_paths=engram_paths,
            ollama_model=ollama_model,
            ollama_url=ollama_url,
            max_evidence_cards=max_evidence_cards,
            output_dir=output_dir,
        )
        self.evidence_cards = filter_evidence_cards(self.evidence_cards)
        self.corpus_stats = collect_source_pages_from_artifacts(artifact_paths)

    def answer(self, query: str) -> Dict[str, Any]:
        kind = query_kind(query)

        if kind == "corpus_stats":
            result = corpus_stats_answer(self.corpus_stats)
            result["query"] = query
            self.log_query(result)
            return result

        evidence_kind, cards = v1.retrieve_evidence(self.evidence_cards, query, max_cards=self.max_evidence_cards)
        if evidence_kind != kind:
            evidence_kind = kind

        should_skip_llm = self.llm_policy == "never" or (
            self.llm_policy == "auto" and evidence_kind in self.fast_task_types
        )

        if should_skip_llm:
            answer = deterministic_answer_v2(query, evidence_kind, cards, self.corpus_stats)
            result = {
                "answer": answer,
                "response": answer,
                "query": query,
                "task_type": evidence_kind,
                "model": "deterministic_fast_path",
                "llm_error": "",
                "fallback_used": False,
                "evidence_card_count": len(cards),
                "citations": v1.build_citations(cards),
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

        prompt = v1.build_prompt(query, evidence_kind, cards, self.engram_guidance)
        answer, llm_error = v1.call_ollama(prompt, self.ollama_model, self.ollama_url)
        fallback_used = False
        if not answer:
            fallback_used = True
            answer = deterministic_answer_v2(query, evidence_kind, cards, self.corpus_stats)

        result = {
            "answer": answer,
            "response": answer,
            "query": query,
            "task_type": evidence_kind,
            "model": self.ollama_model,
            "llm_error": llm_error,
            "fallback_used": fallback_used,
            "evidence_card_count": len(cards),
            "citations": v1.build_citations(cards),
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


def deterministic_answer_v2(query: str, kind: str, cards: List[v1.EvidenceCard], stats: Mapping[str, Any]) -> str:
    if kind == "corpus_stats":
        return corpus_stats_answer(stats)["answer"]
    return v1.deterministic_answer(query, kind, cards)


def serve(
    host: str,
    port: int,
    artifact_paths: List[str],
    engram_paths: List[str],
    ollama_model: str,
    ollama_url: str,
    max_evidence_cards: int,
    output_dir: str,
    llm_policy: str = "auto",
    fast_task_types: Optional[List[str]] = None,
) -> None:
    # Reuse V1 HTTP handler, but update the advertised model id.
    v1.MODEL_ID = MODEL_ID
    v1.MODULE = MODULE
    state = BridgeStateV2(
        artifact_paths=artifact_paths,
        engram_paths=engram_paths,
        ollama_model=ollama_model,
        ollama_url=ollama_url,
        max_evidence_cards=max_evidence_cards,
        output_dir=output_dir,
        llm_policy=llm_policy,
        fast_task_types=fast_task_types,
    )
    server = ThreadingHTTPServer((host, port), v1.Handler)
    server.state = state  # type: ignore[attr-defined]
    print("status=TRACE_NET_OPENWEBUI_GEMMA4_ENGRAM_BRIDGE_V2_STARTED", flush=True)
    print("quality_status=PASS", flush=True)
    print(f"host={host}", flush=True)
    print(f"port={port}", flush=True)
    print(f"model_id={MODEL_ID}", flush=True)
    print(f"ollama_model={ollama_model}", flush=True)
    print(f"evidence_card_count={len(state.evidence_cards)}", flush=True)
    print(f"source_page_count={state.corpus_stats.get('source_page_count')}", flush=True)
    print(f"llm_policy={llm_policy}", flush=True)
    server.serve_forever()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net Open WebUI Gemma4+Engram bridge v2")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--ollama-model", default="gemma4:26b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--artifact", action="append", default=None)
    parser.add_argument("--engram", action="append", default=None)
    parser.add_argument("--max-evidence-cards", type=int, default=10)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/openwebui_gemma4_engram_bridge_v2")
    parser.add_argument("--llm-policy", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--fast-task-types", default="corpus_stats", help="Comma-separated task types to answer deterministically when --llm-policy auto.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    fast_task_types = [x.strip() for x in args.fast_task_types.split(",") if x.strip()]
    serve(
        host=args.host,
        port=args.port,
        artifact_paths=args.artifact or v1.default_artifact_paths(),
        engram_paths=args.engram or v1.default_engram_paths(),
        ollama_model=args.ollama_model,
        ollama_url=args.ollama_url,
        max_evidence_cards=args.max_evidence_cards,
        output_dir=args.output_dir,
        llm_policy=args.llm_policy,
        fast_task_types=fast_task_types,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
