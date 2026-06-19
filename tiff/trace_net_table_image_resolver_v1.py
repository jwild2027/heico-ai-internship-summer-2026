"""TRACE-Net Table Image Resolver v1.

This module maps table/page identifiers to local TIFF/page-image files so later
Table Line Geometry passes can run real morphology instead of relying only on
OCR/table-normalizer fallback geometry.

Safety contract:
- read-only local artifact resolver
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_image_resolver_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_image_resolver_v1_quality"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PATH_FIELD_NAMES = {
    "image_path",
    "image_file",
    "image_uri",
    "page_image_path",
    "page_image_file",
    "page_image_uri",
    "tiff_path",
    "tif_path",
    "tiff_file",
    "source_image_path",
    "source_page_image_path",
    "source_tiff_path",
    "source_file_path",
    "source_path",
    "file_path",
    "path",
    "local_path",
    "page_raster_path",
    "raster_path",
    "png_path",
    "jpg_path",
}

ID_FIELD_NAMES = {
    "page_id",
    "source_page_id",
    "source_page_ids",
    "table_id",
    "normalized_table_id",
    "geometry_card_id",
    "review_task_id",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    joined = "|".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def load_json(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def quality_status(payload: Mapping[str, Any]) -> str:
    status = payload.get("quality_status") or payload.get("status")
    if isinstance(status, str):
        return status.upper()
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        status = summary.get("quality_status") or summary.get("status")
        if isinstance(status, str):
            return status.upper()
    return "UNKNOWN"


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def iter_dicts(obj: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def normalize_path_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lower = text.lower()
    if lower.startswith(("http://", "https://", "s3://", "gs://")):
        return text
    suffix = Path(text.replace("\\", "/")).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return text
    return None


def collect_path_hints(obj: Any) -> List[str]:
    hints: List[str] = []
    seen = set()
    for d in iter_dicts(obj):
        for key, value in d.items():
            key_l = str(key).lower()
            if key_l not in PATH_FIELD_NAMES and not key_l.endswith("_image_path") and not key_l.endswith("_tiff_path"):
                continue
            for item in as_list(value):
                normalized = normalize_path_string(item)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    hints.append(normalized)
    return hints


def collect_table_geometry_cards(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    cards = payload.get("table_geometry_cards")
    if isinstance(cards, list):
        return [dict(c) for c in cards if isinstance(c, Mapping)]
    # Defensive fallback for future schemas.
    candidates: List[Dict[str, Any]] = []
    for d in iter_dicts(payload):
        if d.get("geometry_card_id") or (d.get("table_id") and d.get("cell_record_count") is not None):
            candidates.append(dict(d))
    return candidates


def extract_page_token(page_id: Any) -> Tuple[Optional[str], Optional[int]]:
    if not isinstance(page_id, str) or not page_id.strip():
        return None, None
    text = page_id.strip()
    match = re.search(r"p(\d{3,8})$", text)
    if not match:
        match = re.search(r"(?:page|pg|p)[_\- ]?(\d{1,8})", text, flags=re.IGNORECASE)
    if not match:
        return None, None
    digits = match.group(1)
    try:
        number = int(digits)
    except ValueError:
        number = None
    return f"p{int(digits):06d}" if number is not None else f"p{digits}", number


def candidate_page_strings(page_id: Any) -> List[str]:
    strings: List[str] = []
    if isinstance(page_id, str) and page_id:
        strings.append(page_id.lower())
        token, number = extract_page_token(page_id)
        if token:
            strings.append(token.lower())
            strings.append(token.lower().replace("p", "page_", 1))
            strings.append(token.lower().replace("p", "page-", 1))
            strings.append(token.lower().replace("p", "page", 1))
            strings.append(token[1:])
        if number is not None:
            strings.extend([
                f"page_{number}",
                f"page-{number}",
                f"page{number}",
                f"p{number}",
                f"pg_{number}",
                f"pg-{number}",
                f"{number:03d}",
                f"{number:04d}",
                f"{number:05d}",
                f"{number:06d}",
            ])
    # Preserve order and uniqueness.
    out: List[str] = []
    seen = set()
    for s in strings:
        s = str(s).lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def score_image_path(path: Path | str, page_id: Any, table_id: Any = None) -> int:
    text = str(path).replace("\\", "/").lower()
    name = Path(text).name.lower()
    stem = Path(text).stem.lower()
    score = 0

    if isinstance(page_id, str) and page_id.lower() in text:
        score += 110
    for token in candidate_page_strings(page_id):
        if token in name:
            score += 80
        elif token in stem:
            score += 65
        elif token in text:
            score += 45
    if isinstance(table_id, str) and table_id.lower() in text:
        score += 25
    if any(word in text for word in ("page", "pages", "raster", "image", "tiff", "tif")):
        score += 12
    if Path(text).suffix.lower() in {".tif", ".tiff"}:
        score += 8
    return score


@dataclass(frozen=True)
class ImageCandidate:
    image_path: str
    candidate_source: str
    match_score: int
    path_exists: bool
    file_size_bytes: Optional[int]
    suffix: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_path": self.image_path,
            "candidate_source": self.candidate_source,
            "match_score": self.match_score,
            "path_exists": self.path_exists,
            "file_size_bytes": self.file_size_bytes,
            "suffix": self.suffix,
        }


def resolve_path_hint(hint: str, image_root: Path) -> Path:
    p = Path(hint)
    if p.is_absolute():
        return p
    return image_root / p


def scan_image_files(image_root: Optional[Path], max_image_files: int) -> List[Path]:
    if image_root is None:
        return []
    root = Path(image_root)
    if not root.exists():
        return []
    results: List[Path] = []
    for p in root.rglob("*"):
        if len(results) >= max_image_files:
            break
        if not p.is_file():
            continue
        if p.suffix.lower() in IMAGE_EXTENSIONS:
            results.append(p)
    return results


def collect_context_records_by_page_and_table(payloads: Sequence[Mapping[str, Any]]) -> Dict[str, List[Mapping[str, Any]]]:
    index: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for payload in payloads:
        for d in iter_dicts(payload):
            if not isinstance(d, Mapping):
                continue
            page_ids = []
            for key in ("page_id", "source_page_id", "source_page_ids"):
                for item in as_list(d.get(key)):
                    if isinstance(item, str) and item:
                        page_ids.append(item)
            table_ids = []
            for key in ("table_id", "normalized_table_id"):
                for item in as_list(d.get(key)):
                    if isinstance(item, str) and item:
                        table_ids.append(item)
            for page_id in page_ids:
                index[f"page::{page_id}"].append(d)
            for table_id in table_ids:
                index[f"table::{table_id}"].append(d)
    return index


def unique_candidates(candidates: Iterable[ImageCandidate]) -> List[ImageCandidate]:
    best_by_path: Dict[str, ImageCandidate] = {}
    for c in candidates:
        existing = best_by_path.get(c.image_path)
        if existing is None or c.match_score > existing.match_score or (c.path_exists and not existing.path_exists):
            best_by_path[c.image_path] = c
    return sorted(best_by_path.values(), key=lambda c: (c.path_exists, c.match_score, c.file_size_bytes or 0), reverse=True)


def make_candidate(path: Path, source: str, page_id: Any, table_id: Any) -> ImageCandidate:
    exists = path.exists() and path.is_file()
    size = path.stat().st_size if exists else None
    return ImageCandidate(
        image_path=str(path).replace("\\", "/"),
        candidate_source=source,
        match_score=score_image_path(path, page_id, table_id),
        path_exists=exists,
        file_size_bytes=size,
        suffix=path.suffix.lower(),
    )


def build_resolution_card(
    card: Mapping[str, Any],
    context_index: Mapping[str, List[Mapping[str, Any]]],
    scanned_images: Sequence[Path],
    image_root: Optional[Path],
    max_candidates_per_card: int,
) -> Dict[str, Any]:
    page_id = card.get("page_id") or next(iter(as_list(card.get("source_page_ids"))), None)
    table_id = card.get("table_id") or card.get("normalized_table_id")
    table_type = card.get("table_type")

    candidate_records: List[Tuple[str, Mapping[str, Any]]] = [("table_geometry_card", card)]
    if page_id:
        candidate_records.extend(("context_by_page", r) for r in context_index.get(f"page::{page_id}", [])[:200])
    if table_id:
        candidate_records.extend(("context_by_table", r) for r in context_index.get(f"table::{table_id}", [])[:200])

    candidates: List[ImageCandidate] = []
    root = image_root or Path(".")
    for source, record in candidate_records:
        for hint in collect_path_hints(record):
            p = resolve_path_hint(hint, root)
            candidates.append(make_candidate(p, source, page_id, table_id))

    # Scanned image fallback: only keep files with some positive score for this page.
    for path in scanned_images:
        score = score_image_path(path, page_id, table_id)
        if score > 0:
            candidates.append(make_candidate(path, "image_root_scan", page_id, table_id))

    candidates = unique_candidates(candidates)
    selected: Optional[ImageCandidate] = None
    for candidate in candidates:
        if candidate.path_exists and candidate.match_score > 0:
            selected = candidate
            break

    review_flags: List[str] = []
    recommended_actions: List[str] = []
    if image_root is None:
        review_flags.append("image_root_not_provided")
        recommended_actions.append("provide_image_root_or_page_image_manifest")
    elif not Path(image_root).exists():
        review_flags.append("image_root_missing")
        recommended_actions.append("provide_existing_image_root")
    if not candidates:
        review_flags.append("no_image_candidates_found")
        recommended_actions.append("add_page_id_to_image_manifest")
    elif selected is None:
        review_flags.append("image_candidates_found_but_unresolved")
        recommended_actions.append("verify_candidate_image_paths")
    if selected and selected.match_score < 60:
        review_flags.append("low_confidence_image_resolution")
        recommended_actions.append("verify_image_path_matches_page_id")

    if selected:
        status = "RESOLVED"
        confidence = min(1.0, round(selected.match_score / 120.0, 3))
    else:
        status = "UNRESOLVED"
        confidence = 0.0

    source_page_ids = list(dict.fromkeys([x for x in as_list(card.get("source_page_ids")) if isinstance(x, str)] + ([page_id] if isinstance(page_id, str) else [])))

    return {
        "resolver_card_id": stable_id("table_image_resolver", page_id, table_id),
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "source_page_ids": source_page_ids,
        "table_id": table_id,
        "table_type": table_type,
        "source_geometry_card_id": card.get("geometry_card_id"),
        "source_geometry_confidence": card.get("geometry_confidence"),
        "source_review_required": bool(card.get("review_required")),
        "cell_record_count": int(card.get("cell_record_count") or 0),
        "row_record_count": int(card.get("row_record_count") or 0),
        "domain_validation": card.get("domain_validation") if isinstance(card.get("domain_validation"), Mapping) else {},
        "image_resolution_status": status,
        "image_resolution_confidence": confidence,
        "resolved_image_path": selected.image_path if selected else None,
        "resolved_image_file_size_bytes": selected.file_size_bytes if selected else None,
        "resolved_image_suffix": selected.suffix if selected else None,
        "candidate_image_count": len(candidates),
        "candidate_images": [c.to_dict() for c in candidates[:max_candidates_per_card]],
        "image_root": str(image_root).replace("\\", "/") if image_root is not None else None,
        "review_required": bool(review_flags),
        "review_flags": sorted(set(review_flags)),
        "recommended_actions": sorted(set(recommended_actions)),
        "read_only_resolution": True,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_resolution_card": False,
    }


def build_report(
    table_line_geometry_path: Path,
    output_dir: Path,
    table_cell_normalizer_path: Optional[Path] = None,
    human_review_queue_path: Optional[Path] = None,
    image_root: Optional[Path] = None,
    max_image_files: int = 200000,
    max_candidates_per_card: int = 10,
    thresholds: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    thresholds = dict(thresholds or {})
    tlg = load_json(table_line_geometry_path)
    source_payloads: List[Mapping[str, Any]] = [tlg]
    table_cell_normalizer_quality = None
    human_review_queue_quality = None
    if table_cell_normalizer_path and Path(table_cell_normalizer_path).exists():
        normalizer = load_json(table_cell_normalizer_path)
        table_cell_normalizer_quality = quality_status(normalizer)
        source_payloads.append(normalizer)
    if human_review_queue_path and Path(human_review_queue_path).exists():
        hrq = load_json(human_review_queue_path)
        human_review_queue_quality = quality_status(hrq)
        source_payloads.append(hrq)

    source_cards = collect_table_geometry_cards(tlg)
    context_index = collect_context_records_by_page_and_table(source_payloads)
    scanned_images = scan_image_files(image_root, max_image_files)

    resolver_cards = [
        build_resolution_card(card, context_index, scanned_images, image_root, max_candidates_per_card)
        for card in source_cards
    ]

    summary = make_summary(
        resolver_cards=resolver_cards,
        source_cards=source_cards,
        source_quality_status=quality_status(tlg),
        table_cell_normalizer_quality=table_cell_normalizer_quality,
        human_review_queue_quality=human_review_queue_quality,
        scanned_image_count=len(scanned_images),
        image_root=image_root,
    )
    checks, fail_reasons = evaluate_checks(summary, thresholds)
    qstatus = "PASS" if not fail_reasons else "FAIL"
    summary["quality_status"] = qstatus
    summary["quality_fail_reasons"] = fail_reasons
    summary["status"] = "TABLE_IMAGE_RESOLVER_BUILT" if qstatus == "PASS" else "TABLE_IMAGE_RESOLVER_NOT_READY"

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_image_resolver_v1.json"
    cards_path = output_dir / "trace_net_table_image_resolver_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_image_resolver_v1_summary.json"
    quality_path = output_dir / "trace_net_table_image_resolver_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_image_resolver_v1_manifest.json"

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "status": summary["status"],
        "quality_status": qstatus,
        "summary": summary,
        "checks": checks,
        "table_image_resolution_cards": resolver_cards,
        "source_artifacts": {
            "table_line_geometry": str(table_line_geometry_path).replace("\\", "/"),
            "table_cell_normalizer": str(table_cell_normalizer_path).replace("\\", "/") if table_cell_normalizer_path else None,
            "human_review_queue": str(human_review_queue_path).replace("\\", "/") if human_review_queue_path else None,
        },
        "safety_contract": {
            "read_only_resolver": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
    }

    quality_payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "status": qstatus,
        "quality_status": qstatus,
        "summary": summary,
        "checks": checks,
        "quality_errors": fail_reasons,
    }
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now_iso(),
        "report_path": str(report_path).replace("\\", "/"),
        "cards_path": str(cards_path).replace("\\", "/"),
        "summary_path": str(summary_path).replace("\\", "/"),
        "quality_path": str(quality_path).replace("\\", "/"),
        "image_root": str(image_root).replace("\\", "/") if image_root else None,
    }

    write_json(report_path, report)
    write_jsonl(cards_path, resolver_cards)
    write_json(summary_path, summary)
    write_json(quality_path, quality_payload)
    write_json(manifest_path, manifest)
    return report


def make_summary(
    resolver_cards: Sequence[Mapping[str, Any]],
    source_cards: Sequence[Mapping[str, Any]],
    source_quality_status: str,
    table_cell_normalizer_quality: Optional[str],
    human_review_queue_quality: Optional[str],
    scanned_image_count: int,
    image_root: Optional[Path],
) -> Dict[str, Any]:
    resolved_cards = [c for c in resolver_cards if c.get("image_resolution_status") == "RESOLVED"]
    unresolved_cards = [c for c in resolver_cards if c.get("image_resolution_status") != "RESOLVED"]
    part_number_cards = [c for c in resolver_cards if (c.get("domain_validation") or {}).get("part_number_count", 0)]
    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_quality_status": source_quality_status,
        "table_cell_normalizer_quality_status": table_cell_normalizer_quality,
        "human_review_queue_quality_status": human_review_queue_quality,
        "source_table_geometry_card_count": len(source_cards),
        "resolver_card_count": len(resolver_cards),
        "resolved_image_card_count": len(resolved_cards),
        "unresolved_image_card_count": len(unresolved_cards),
        "review_required_card_count": sum(1 for c in resolver_cards if c.get("review_required")),
        "part_number_table_card_count": len(part_number_cards),
        "candidate_image_total_count": sum(int(c.get("candidate_image_count") or 0) for c in resolver_cards),
        "scanned_image_file_count": scanned_image_count,
        "image_root": str(image_root).replace("\\", "/") if image_root is not None else None,
        "image_root_exists": bool(image_root and Path(image_root).exists()),
        "resolution_status_counts": dict(Counter(c.get("image_resolution_status") for c in resolver_cards)),
        "review_flag_counts": dict(Counter(flag for c in resolver_cards for flag in (c.get("review_flags") or []))),
        "recommended_action_counts": dict(Counter(action for c in resolver_cards for action in (c.get("recommended_actions") or []))),
        "unsafe_resolution_card_count": sum(1 for c in resolver_cards if c.get("unsafe_resolution_card")),
        "answer_permission_count": sum(1 for c in resolver_cards if c.get("answer_permission")),
        "can_answer_directly_count": sum(1 for c in resolver_cards if c.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for c in resolver_cards if c.get("can_prove_claims")),
        "retrieval_only_answer_allowed_count": sum(1 for c in resolver_cards if c.get("retrieval_only_answer_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for c in resolver_cards if c.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": sum(int(c.get("source_truth_mutations_performed") or 0) for c in resolver_cards),
        "postgres_write_attempt_count": sum(int(c.get("postgres_write_attempt_count") or 0) for c in resolver_cards),
        "qdrant_write_attempt_count": sum(int(c.get("qdrant_write_attempt_count") or 0) for c in resolver_cards),
        "opensearch_write_attempt_count": sum(int(c.get("opensearch_write_attempt_count") or 0) for c in resolver_cards),
    }
    return summary


def evaluate_checks(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Tuple[Dict[str, bool], List[str]]:
    required_source_pass = bool(thresholds.get("require_table_line_geometry_quality_pass"))
    require_no_answer_permission = bool(thresholds.get("require_no_answer_permission"))
    checks = {
        "schema_version_ok": summary.get("schema_version") == SCHEMA_VERSION,
        "source_quality_pass": (not required_source_pass) or summary.get("source_quality_status") == "PASS",
        "min_source_cards_met": int(summary.get("source_table_geometry_card_count") or 0) >= int(thresholds.get("min_source_cards", 0)),
        "min_resolver_cards_met": int(summary.get("resolver_card_count") or 0) >= int(thresholds.get("min_resolver_cards", 0)),
        "min_resolved_image_cards_met": int(summary.get("resolved_image_card_count") or 0) >= int(thresholds.get("min_resolved_image_cards", 0)),
        "unsafe_cards_within_limit": int(summary.get("unsafe_resolution_card_count") or 0) <= int(thresholds.get("max_unsafe_resolution_cards", 0)),
        "answer_permission_within_limit": int(summary.get("answer_permission_count") or 0) <= int(thresholds.get("max_answer_permission_count", 0)),
        "source_truth_mutation_allowed_within_limit": int(summary.get("source_truth_mutation_allowed_count") or 0) <= int(thresholds.get("max_source_truth_mutation_allowed", 0)),
        "write_attempts_zero": int(summary.get("postgres_write_attempt_count") or 0) == 0
        and int(summary.get("qdrant_write_attempt_count") or 0) == 0
        and int(summary.get("opensearch_write_attempt_count") or 0) == 0,
        "can_answer_directly_zero": int(summary.get("can_answer_directly_count") or 0) == 0,
        "can_prove_claims_zero": int(summary.get("can_prove_claims_count") or 0) == 0,
    }
    if require_no_answer_permission:
        checks["answer_permission_zero_required"] = int(summary.get("answer_permission_count") or 0) == 0
    fail_reasons = [name for name, ok in checks.items() if not ok]
    return checks, fail_reasons


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_source_cards": args.min_source_cards,
        "min_resolver_cards": args.min_resolver_cards,
        "min_resolved_image_cards": args.min_resolved_image_cards,
        "max_unsafe_resolution_cards": args.max_unsafe_resolution_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_line_geometry_quality_pass": args.require_table_line_geometry_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Table Image Resolver v1")
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--table-cell-normalizer", type=Path)
    parser.add_argument("--human-review-queue", type=Path)
    parser.add_argument("--image-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-image-files", type=int, default=200000)
    parser.add_argument("--max-candidates-per-card", type=int, default=10)
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-resolver-cards", type=int, default=1)
    parser.add_argument("--min-resolved-image-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-resolution-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def print_report(report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("TRACE-Net Table Image Resolver v1")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for key in [
        "source_table_geometry_card_count",
        "resolver_card_count",
        "resolved_image_card_count",
        "unresolved_image_card_count",
        "scanned_image_file_count",
        "candidate_image_total_count",
        "review_required_card_count",
        "part_number_table_card_count",
        "unsafe_resolution_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}:", summary.get(key))
    # Output paths are written under the CLI --output-dir.


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        table_cell_normalizer_path=args.table_cell_normalizer,
        human_review_queue_path=args.human_review_queue,
        image_root=args.image_root,
        output_dir=args.output_dir,
        max_image_files=args.max_image_files,
        max_candidates_per_card=args.max_candidates_per_card,
        thresholds=thresholds_from_args(args),
    )
    print_report(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
