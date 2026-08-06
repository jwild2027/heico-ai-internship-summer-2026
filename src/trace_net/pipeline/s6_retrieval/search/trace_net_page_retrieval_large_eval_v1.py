from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_page_retrieval_large_eval_v1"
DEFAULT_COLLECTION = "trace_net_page_retrieval_profiles_ollama_bge_m3_v1"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "bge-m3:latest"

PAGE_ID_RE = re.compile(r"p(\d{6})$")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def compact_text(value: Any, limit: int = 900) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def page_number_from_page_id(page_id: str) -> int | None:
    m = PAGE_ID_RE.search(page_id or "")
    if not m:
        return None
    return int(m.group(1))


def normalize_page_id(page_number: int) -> str:
    return f"t_p_120_1176_p{page_number:06d}"


def profile_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("page_profiles", "records", "profiles", "profile_records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    raise KeyError("Could not find page profile records in profiles artifact")


def nested_values(obj: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield p, v
            yield from nested_values(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            yield p, v
            yield from nested_values(v, p)


def first_by_key_fragment(record: dict[str, Any], fragments: tuple[str, ...]) -> Any:
    for path, value in nested_values(record):
        lower = path.lower()
        if any(fragment in lower for fragment in fragments):
            if value not in (None, "", [], {}):
                return value
    return None


def all_by_key_fragment(record: dict[str, Any], fragments: tuple[str, ...], max_items: int = 12) -> list[str]:
    out: list[str] = []
    for path, value in nested_values(record):
        lower = path.lower()
        if not any(fragment in lower for fragment in fragments):
            continue
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            for item in value:
                text = compact_text(item, 220)
                if text and text not in out:
                    out.append(text)
                if len(out) >= max_items:
                    return out
        else:
            text = compact_text(value, 220)
            if text and text not in out:
                out.append(text)
            if len(out) >= max_items:
                return out
    return out


def has_truthy_key(record: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for path, value in nested_values(record):
        leaf = path.split(".")[-1].split("[")[0].lower()
        if leaf in keys and value not in (None, False, "", [], {}):
            return True
    return False


def infer_blank_from_profile(profile: dict[str, Any]) -> bool:
    text = json.dumps(profile, ensure_ascii=False).lower()
    return any(token in text for token in [
        '"role": "blank"', "role: blank", "empty_or_blank_page", "blank page", "empty page"
    ])


def load_metadata_zip_pages(metadata_zip: str | Path, first_pages: int) -> dict[str, dict[str, Any]]:
    path = Path(metadata_zip)
    if not path.exists():
        raise FileNotFoundError(f"Missing metadata zip: {path}")
    out: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(path, "r") as zf:
        infos = {info.filename: info for info in zf.infolist()}
        for page_number in range(1, first_pages + 1):
            entry = f"{page_number:08d}.tif"
            info = infos.get(entry)
            page_id = normalize_page_id(page_number)
            record: dict[str, Any] = {
                "page_id": page_id,
                "page_number": page_number,
                "zip_entry_name": entry,
                "zip_entry_present": bool(info),
                "zip_entry_size_bytes": int(info.file_size) if info else None,
                "blank_by_zip_size": bool(info and info.file_size <= 5000),
                "blank_by_image_heuristic": None,
                "image_ink_ratio": None,
                "image_width": None,
                "image_height": None,
            }
            if info:
                try:
                    from PIL import Image  # type: ignore
                    with zf.open(info, "r") as raw:
                        img = Image.open(BytesIO(raw.read()))
                        img = img.convert("L")
                        record["image_width"], record["image_height"] = img.size
                        small = img.resize((min(256, img.size[0]), max(1, int(img.size[1] * min(256, img.size[0]) / max(1, img.size[0])))))
                        pixels = list(small.getdata())
                        dark = sum(1 for p in pixels if p < 245)
                        ink_ratio = dark / max(1, len(pixels))
                        record["image_ink_ratio"] = round(float(ink_ratio), 6)
                        # Real blank pages in this source package are tiny and visually near-empty.
                        record["blank_by_image_heuristic"] = ink_ratio < 0.002
                except Exception as exc:
                    record["image_heuristic_error"] = f"{type(exc).__name__}: {exc}"
            out[page_id] = record
    return out


def build_query_from_profile(page_id: str, profile: dict[str, Any], zip_record: dict[str, Any]) -> dict[str, Any]:
    page_number = page_number_from_page_id(page_id)
    role = first_by_key_fragment(profile, ("page_role", "role"))
    subrole = first_by_key_fragment(profile, ("page_subrole", "subrole"))
    retrieval_summary = first_by_key_fragment(profile, ("retrieval_summary", "short_summary", "summary"))
    retrieval_cues = all_by_key_fragment(profile, ("retrieval_cues", "query_cues", "answerable_questions", "important_terms"), max_items=8)
    embedding_text = profile.get("embedding_text") or first_by_key_fragment(profile, ("embedding_text",))
    has_context_v2 = (
        bool(profile.get("has_context_v2"))
        or bool(profile.get("context_v2_present"))
        or "context_v2" in json.dumps(profile, ensure_ascii=False).lower()
    )
    blank_expected = bool(
        infer_blank_from_profile(profile)
        or zip_record.get("blank_by_zip_size")
        or zip_record.get("blank_by_image_heuristic")
    )

    role_text = compact_text(role, 120)
    subrole_text = compact_text(subrole, 160)
    summary_text = compact_text(retrieval_summary, 360)
    cue_text = "; ".join(retrieval_cues[:6])
    fallback_text = compact_text(embedding_text, 500)

    if blank_expected:
        semantic_query = (
            f"Find the blank or empty page in the EMB CMM ATA 25-21-00 technical manual. "
            f"This page should have no substantive content. Page number {page_number}."
        )
        llm_question = (
            f"What is on page {page_number} of EMB CMM ATA 25-21-00 REV.4? "
            f"If it is blank, say the page is blank."
        )
        expected_answer_behavior = "LLM_SHOULD_STATE_PAGE_IS_BLANK_OR_EMPTY"
    else:
        parts = [
            "Find the technical manual page that best matches this page-context card.",
            f"Manual: EMB CMM ATA 25-21-00 REV.4.",
        ]
        if role_text:
            parts.append(f"Role: {role_text}.")
        if subrole_text:
            parts.append(f"Subrole: {subrole_text}.")
        if summary_text:
            parts.append(f"Summary: {summary_text}.")
        if cue_text:
            parts.append(f"Retrieval cues/questions: {cue_text}.")
        elif fallback_text:
            parts.append(f"Profile text: {fallback_text}.")
        semantic_query = " ".join(parts)
        llm_question = (
            f"What is on page {page_number} of EMB CMM ATA 25-21-00 REV.4? "
            f"Use only source-traced evidence; if the page is blank, say it is blank."
        )
        expected_answer_behavior = "LLM_SHOULD_SUMMARIZE_PAGE_CONTEXT_WITH_SOURCE_TRACE"

    return {
        "page_id": page_id,
        "page_number": page_number,
        "query_id": f"page_retrieval_eval::{page_id}",
        "semantic_retrieval_query": semantic_query,
        "llm_question": llm_question,
        "expected_target_page_id": page_id,
        "expected_answer_behavior": expected_answer_behavior,
        "blank_expected": blank_expected,
        "blank_detection": {
            "blank_by_profile": infer_blank_from_profile(profile),
            "blank_by_zip_size": bool(zip_record.get("blank_by_zip_size")),
            "blank_by_image_heuristic": zip_record.get("blank_by_image_heuristic"),
            "image_ink_ratio": zip_record.get("image_ink_ratio"),
            "zip_entry_size_bytes": zip_record.get("zip_entry_size_bytes"),
        },
        "profile_signals": {
            "has_context_v2": has_context_v2,
            "role": role_text or None,
            "subrole": subrole_text or None,
            "retrieval_summary_preview": summary_text or None,
            "retrieval_cues": retrieval_cues[:8],
        },
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only": True,
        "source_truth_mutation_allowed": False,
    }


def ollama_embed_batch(texts: list[str], *, ollama_url: str, model: str, timeout: int) -> list[list[float]]:
    endpoint = ollama_url.rstrip("/") + "/api/embed"
    payload = {"model": model, "input": texts}
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    embeddings = data.get("embeddings") or []
    if len(embeddings) != len(texts):
        raise RuntimeError(f"Ollama returned {len(embeddings)} embeddings for {len(texts)} texts")
    return embeddings


def qdrant_query_points(client: Any, *, collection: str, vector: list[float], limit: int) -> list[Any]:
    if hasattr(client, "query_points"):
        result = client.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return list(getattr(result, "points", result))
    return list(client.search(
        collection_name=collection,
        query_vector=vector,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    ))


def run_qdrant_eval(
    query_records: list[dict[str, Any]],
    *,
    qdrant_url: str,
    collection: str,
    ollama_url: str,
    ollama_model: str,
    top_k: int,
    batch_size: int,
    timeout: int,
    progress: bool = False,
) -> list[dict[str, Any]]:
    try:
        from qdrant_client import QdrantClient  # type: ignore
    except Exception as exc:
        raise RuntimeError("qdrant_client is required for --run-qdrant-eval") from exc
    client = QdrantClient(url=qdrant_url)
    evaluated: list[dict[str, Any]] = []
    for start in range(0, len(query_records), batch_size):
        batch = query_records[start:start + batch_size]
        if progress:
            print(f"TRACE-Net large retrieval eval: embedding/querying {start}/{len(query_records)}")
        embeddings = ollama_embed_batch(
            [r["semantic_retrieval_query"] for r in batch],
            ollama_url=ollama_url,
            model=ollama_model,
            timeout=timeout,
        )
        for record, vector in zip(batch, embeddings):
            hits_raw = qdrant_query_points(client, collection=collection, vector=vector, limit=top_k)
            hits: list[dict[str, Any]] = []
            target_rank: int | None = None
            target_page_id = record["expected_target_page_id"]
            answer_capable_payload_count = 0
            claim_proof_payload_count = 0
            for rank, hit in enumerate(hits_raw, 1):
                payload = getattr(hit, "payload", None) or {}
                page_id = payload.get("page_id")
                score = getattr(hit, "score", None)
                if page_id == target_page_id and target_rank is None:
                    target_rank = rank
                if payload.get("can_answer_directly") is True or payload.get("answer_capable") is True:
                    answer_capable_payload_count += 1
                if payload.get("can_prove_claims") is True or payload.get("claim_proof") is True:
                    claim_proof_payload_count += 1
                hits.append({
                    "rank": rank,
                    "score": float(score) if score is not None else None,
                    "page_id": page_id,
                    "has_context_v2": bool(payload.get("has_context_v2") or payload.get("context_v2_present")),
                    "payload_keys": sorted(payload.keys())[:80],
                })
            evaluated_record = dict(record)
            evaluated_record.update({
                "evaluated": True,
                "qdrant_collection": collection,
                "top_k": top_k,
                "target_rank": target_rank,
                "target_hit_at_1": target_rank == 1,
                "target_hit_at_3": bool(target_rank and target_rank <= 3),
                "target_hit_at_5": bool(target_rank and target_rank <= 5),
                "target_hit_at_10": bool(target_rank and target_rank <= 10),
                "target_hit_at_k": bool(target_rank and target_rank <= top_k),
                "top_hits": hits,
                "answer_capable_payload_count": answer_capable_payload_count,
                "claim_proof_payload_count": claim_proof_payload_count,
            })
            evaluated.append(evaluated_record)
    if progress:
        print(f"TRACE-Net large retrieval eval: embedding/querying {len(query_records)}/{len(query_records)}")
    return evaluated


def summarize(records: list[dict[str, Any]], *, first_pages: int, collection: str | None = None) -> dict[str, Any]:
    evaluated = [r for r in records if r.get("evaluated")]
    blank_records = [r for r in records if r.get("blank_expected")]
    context_v2_records = [r for r in records if r.get("profile_signals", {}).get("has_context_v2")]
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "first_pages_requested": first_pages,
        "query_record_count": len(records),
        "evaluated_record_count": len(evaluated),
        "blank_expected_count": len(blank_records),
        "context_v2_query_count": len(context_v2_records),
        "llm_should_say_blank_count": len(blank_records),
        "qdrant_collection": collection,
        "answer_capable_payload_count": sum(int(r.get("answer_capable_payload_count") or 0) for r in evaluated),
        "claim_proof_payload_count": sum(int(r.get("claim_proof_payload_count") or 0) for r in evaluated),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly") is True),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims") is True),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed") is True),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    if evaluated:
        for k, pred in [
            ("target_hit_at_1_count", lambda r: r.get("target_hit_at_1")),
            ("target_hit_at_3_count", lambda r: r.get("target_hit_at_3")),
            ("target_hit_at_5_count", lambda r: r.get("target_hit_at_5")),
            ("target_hit_at_10_count", lambda r: r.get("target_hit_at_10")),
            ("target_hit_at_k_count", lambda r: r.get("target_hit_at_k")),
        ]:
            count = sum(1 for r in evaluated if pred(r))
            summary[k] = count
            summary[k.replace("_count", "_rate")] = round(count / max(1, len(evaluated)), 6)
        blank_eval = [r for r in evaluated if r.get("blank_expected")]
        summary["blank_target_hit_at_k_count"] = sum(1 for r in blank_eval if r.get("target_hit_at_k"))
        summary["blank_evaluated_count"] = len(blank_eval)
    return summary


@dataclass
class QualityThresholds:
    min_query_records: int = 1
    min_blank_queries: int = 0
    min_context_v2_queries: int = 0
    min_evaluated_records: int = 0
    min_target_hit_at_k: int = 0
    max_answer_capable_payloads: int = 0
    max_claim_proof_payloads: int = 0
    max_source_truth_mutation_allowed: int = 0


def quality_checks(summary: dict[str, Any], thresholds: QualityThresholds) -> list[dict[str, Any]]:
    checks = []
    def add(name: str, ok: bool, detail: str):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    add("query_record_count", summary.get("query_record_count", 0) >= thresholds.min_query_records,
        f"records={summary.get('query_record_count', 0)} minimum={thresholds.min_query_records}")
    add("blank_expected_count", summary.get("blank_expected_count", 0) >= thresholds.min_blank_queries,
        f"blank={summary.get('blank_expected_count', 0)} minimum={thresholds.min_blank_queries}")
    add("context_v2_query_count", summary.get("context_v2_query_count", 0) >= thresholds.min_context_v2_queries,
        f"context_v2={summary.get('context_v2_query_count', 0)} minimum={thresholds.min_context_v2_queries}")
    add("evaluated_record_count", summary.get("evaluated_record_count", 0) >= thresholds.min_evaluated_records,
        f"evaluated={summary.get('evaluated_record_count', 0)} minimum={thresholds.min_evaluated_records}")
    add("target_hit_at_k_count", summary.get("target_hit_at_k_count", 0) >= thresholds.min_target_hit_at_k,
        f"hits={summary.get('target_hit_at_k_count', 0)} minimum={thresholds.min_target_hit_at_k}")
    add("answer_capable_payload_count", summary.get("answer_capable_payload_count", 0) <= thresholds.max_answer_capable_payloads,
        f"answer_capable={summary.get('answer_capable_payload_count', 0)} max={thresholds.max_answer_capable_payloads}")
    add("claim_proof_payload_count", summary.get("claim_proof_payload_count", 0) <= thresholds.max_claim_proof_payloads,
        f"claim_proof={summary.get('claim_proof_payload_count', 0)} max={thresholds.max_claim_proof_payloads}")
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.max_source_truth_mutation_allowed,
        f"source_truth_mutation_allowed={summary.get('source_truth_mutation_allowed_count', 0)} max={thresholds.max_source_truth_mutation_allowed}")
    add("no_write_attempts", summary.get("postgres_write_attempt_count", 0) == 0 and summary.get("qdrant_write_attempt_count", 0) == 0 and summary.get("opensearch_write_attempt_count", 0) == 0,
        "read-only eval")
    return checks


def build_large_eval(
    *,
    metadata_zip: str | Path,
    profiles_path: str | Path,
    output_dir: str | Path,
    first_pages: int,
    run_qdrant: bool,
    qdrant_url: str,
    collection: str,
    ollama_url: str,
    ollama_model: str,
    top_k: int,
    batch_size: int,
    ollama_timeout: int,
    progress: bool,
    thresholds: QualityThresholds,
) -> dict[str, Any]:
    profiles_payload = load_json(profiles_path)
    records = profile_records(profiles_payload)
    by_page = {r.get("page_id"): r for r in records if r.get("page_id")}
    zip_pages = load_metadata_zip_pages(metadata_zip, first_pages)

    query_records: list[dict[str, Any]] = []
    missing_profiles: list[str] = []
    for page_number in range(1, first_pages + 1):
        page_id = normalize_page_id(page_number)
        profile = by_page.get(page_id)
        if not profile:
            missing_profiles.append(page_id)
            continue
        query_records.append(build_query_from_profile(page_id, profile, zip_pages.get(page_id, {})))

    if run_qdrant:
        query_records = run_qdrant_eval(
            query_records,
            qdrant_url=qdrant_url,
            collection=collection,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            top_k=top_k,
            batch_size=batch_size,
            timeout=ollama_timeout,
            progress=progress,
        )

    summary = summarize(query_records, first_pages=first_pages, collection=collection if run_qdrant else None)
    summary["profile_record_count"] = len(records)
    summary["missing_profile_count"] = len(missing_profiles)
    summary["missing_profiles"] = missing_profiles[:30]
    summary["metadata_zip_path"] = str(metadata_zip)
    summary["profiles_path"] = str(profiles_path)
    summary["ollama_model"] = ollama_model if run_qdrant else None
    summary["ollama_url"] = ollama_url if run_qdrant else None
    summary["top_k"] = top_k if run_qdrant else None

    checks = quality_checks(summary, thresholds)
    quality_status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "PAGE_RETRIEVAL_LARGE_EVAL_BUILT",
        "quality_status": quality_status,
        "created_at": now_iso(),
        "summary": summary,
        "quality_checks": checks,
        "query_records": query_records,
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "trace_net_page_retrieval_large_eval_v1.json"
    quality_path = out_dir / "trace_net_page_retrieval_large_eval_v1_quality.json"
    query_jsonl_path = out_dir / "trace_net_page_retrieval_large_eval_v1_queries.jsonl"
    md_path = out_dir / "trace_net_page_retrieval_large_eval_v1.md"
    write_json(report_path, payload)
    write_json(quality_path, {k: payload[k] for k in ["schema_version", "status", "quality_status", "created_at", "summary", "quality_checks"]})
    write_jsonl(query_jsonl_path, query_records)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    payload["report_path"] = str(report_path)
    payload["quality_path"] = str(quality_path)
    payload["query_jsonl_path"] = str(query_jsonl_path)
    payload["markdown_path"] = str(md_path)
    write_json(report_path, payload)
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    s = payload.get("summary", {})
    lines = [
        "# TRACE-Net Page Retrieval Large Eval v1",
        "",
        f"Status: `{payload.get('status')}`",
        f"Quality: `{payload.get('quality_status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "query_record_count", "evaluated_record_count", "blank_expected_count", "context_v2_query_count",
        "target_hit_at_1_count", "target_hit_at_3_count", "target_hit_at_5_count", "target_hit_at_10_count", "target_hit_at_k_count",
        "target_hit_at_1_rate", "target_hit_at_10_rate", "target_hit_at_k_rate",
        "answer_capable_payload_count", "claim_proof_payload_count", "source_truth_mutation_allowed_count",
    ]:
        if key in s:
            lines.append(f"- {key}: `{s.get(key)}`")
    lines += ["", "## Notes", "", "This artifact is retrieval-only. It does not grant answer permission or claim proof authority.", ""]
    return "\n".join(lines)


def check_large_eval_quality(
    *,
    report_path: str | Path,
    thresholds: QualityThresholds,
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = load_json(report_path)
    summary = payload.get("summary") or {}
    checks = quality_checks(summary, thresholds)
    quality_status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": payload.get("status"),
        "quality_status": quality_status,
        "created_at": now_iso(),
        "summary": summary,
        "quality_checks": checks,
    }
    if write_json_report:
        q_path = Path(report_path).with_name("trace_net_page_retrieval_large_eval_v1_quality.json")
        write_json(q_path, report)
        report["quality_path"] = str(q_path)
    return report


def print_summary(payload: dict[str, Any]) -> None:
    s = payload.get("summary", {})
    print("TRACE-Net Page Retrieval Large Eval v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "query_record_count", "evaluated_record_count", "blank_expected_count", "context_v2_query_count",
        "target_hit_at_1_count", "target_hit_at_3_count", "target_hit_at_5_count", "target_hit_at_10_count", "target_hit_at_k_count",
        "target_hit_at_1_rate", "target_hit_at_10_rate", "target_hit_at_k_rate",
        "answer_capable_payload_count", "claim_proof_payload_count", "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count",
    ]:
        if key in s:
            print(f" {key}: {s.get(key)}")
    for key in ("report_path", "quality_path", "query_jsonl_path", "markdown_path"):
        if payload.get(key):
            print(f" {key}: {payload.get(key)}")


def parse_thresholds(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        min_query_records=args.min_query_records,
        min_blank_queries=args.min_blank_queries,
        min_context_v2_queries=args.min_context_v2_queries,
        min_evaluated_records=args.min_evaluated_records,
        min_target_hit_at_k=args.min_target_hit_at_k,
        max_answer_capable_payloads=args.max_answer_capable_payloads,
        max_claim_proof_payloads=args.max_claim_proof_payloads,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
    )


def add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-query-records", type=int, default=1)
    parser.add_argument("--min-blank-queries", type=int, default=0)
    parser.add_argument("--min-context-v2-queries", type=int, default=0)
    parser.add_argument("--min-evaluated-records", type=int, default=0)
    parser.add_argument("--min-target-hit-at-k", type=int, default=0)
    parser.add_argument("--max-answer-capable-payloads", type=int, default=0)
    parser.add_argument("--max-claim-proof-payloads", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)


def main_build(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build one-query-per-page TRACE-Net retrieval eval for first N pages")
    parser.add_argument("--metadata-zip", required=True)
    parser.add_argument("--profiles-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--first-pages", type=int, default=170)
    parser.add_argument("--run-qdrant-eval", action="store_true")
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--ollama-timeout", type=int, default=180)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--quality", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args(argv)
    payload = build_large_eval(
        metadata_zip=args.metadata_zip,
        profiles_path=args.profiles_path,
        output_dir=args.output_dir,
        first_pages=args.first_pages,
        run_qdrant=args.run_qdrant_eval,
        qdrant_url=args.qdrant_url,
        collection=args.collection,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        top_k=args.top_k,
        batch_size=args.batch_size,
        ollama_timeout=args.ollama_timeout,
        progress=args.progress,
        thresholds=parse_thresholds(args),
    )
    print_summary(payload)
    return 0 if payload.get("quality_status") == "PASS" else 2


def main_check(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Page Retrieval Large Eval v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args(argv)
    report = check_large_eval_quality(
        report_path=args.report_path,
        thresholds=parse_thresholds(args),
        write_json_report=args.write_json,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main_build())
