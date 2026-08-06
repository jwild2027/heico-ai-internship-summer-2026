from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

STATUS = "TRACE_NET_IMAGE_ROUTE_MULTI_ROUTE_QUALITY_GATE_CHECKED"
SCHEMA_VERSION = "trace_net_image_route_multi_route_quality_gate_v1"
ROUTE_TYPE = "image_or_diagram"


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _summary_count(data: Dict[str, Any], key: str) -> int:
    try:
        return int((data.get("summary") or {}).get(key, data.get(key, 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _bool(data: Dict[str, Any], key: str) -> bool:
    if key in data:
        return bool(data.get(key))
    return bool((data.get("summary") or {}).get(key))


def evaluate_gate(
    adapter: Dict[str, Any],
    *,
    require_webui_answer_ready: bool = False,
    min_citations: int = 0,
    min_source_trace_ready_citations: int = 0,
    max_unsupported_claims: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    route_type = adapter.get("route_type") or (adapter.get("summary") or {}).get("route_type")
    citations = adapter.get("citations") if isinstance(adapter.get("citations"), list) else []
    answer = str(adapter.get("answer") or "")

    citation_count = len(citations) or _summary_count(adapter, "citation_count")
    source_trace_ready_citation_count = sum(1 for c in citations if c.get("source_trace_ready")) or _summary_count(adapter, "source_trace_ready_citation_count")
    linked_citation_count = sum(1 for c in citations if c.get("linked_part_number")) or _summary_count(adapter, "linked_citation_count")

    unsupported_claim_count = _summary_count(adapter, "unsupported_claim_count")
    llava_only_part_identity_claim_count = _summary_count(adapter, "llava_only_part_identity_claim_count")
    unsafe_record_count = _summary_count(adapter, "unsafe_record_count")
    answer_permission_count = _summary_count(adapter, "answer_permission_count")
    source_truth_mutation_allowed_count = _summary_count(adapter, "source_truth_mutation_allowed_count")
    write_attempt_count = _summary_count(adapter, "write_attempt_count")

    # Defense-in-depth: detect affirmative unsafe claims if a future adapter fails to count them.
    lower = answer.lower()
    affirmative_unsafe_patterns = [
        r"\bis\s+interchangeable\b",
        r"\bare\s+interchangeable\b",
        r"\bapproved\s+replacement\b",
        r"\bsafe\s+to\s+install\b",
        r"\bguaranteed\s+fit\b",
    ]
    inferred_unsafe_claims = sum(1 for pat in affirmative_unsafe_patterns if re.search(pat, lower))
    unsupported_claim_count = max(unsupported_claim_count, inferred_unsafe_claims)

    if re.search(r"part\s+number\s+[0-9]{2,}-[0-9]{2,}-[0-9A-Za-z]{2,}", answer, re.IGNORECASE) and linked_citation_count == 0:
        llava_only_part_identity_claim_count = max(llava_only_part_identity_claim_count, 1)

    checks = {
        "route_type_is_image_or_diagram": route_type == ROUTE_TYPE,
        "adapter_quality_pass": adapter.get("quality_status") == "PASS",
        "webui_answer_ready_required_met": (not require_webui_answer_ready) or bool(adapter.get("webui_answer_ready")),
        "citation_count_min_met": citation_count >= min_citations,
        "source_trace_ready_citation_min_met": source_trace_ready_citation_count >= min_source_trace_ready_citations,
        "linked_citation_present_for_part_identity": linked_citation_count > 0 if re.search(r"part\s+number\s+[0-9]{2,}-[0-9]{2,}-[0-9A-Za-z]{2,}", answer, re.IGNORECASE) else True,
        "unsupported_claim_max_met": unsupported_claim_count <= max_unsupported_claims,
        "llava_only_part_identity_claim_max_met": llava_only_part_identity_claim_count <= max_llava_only_part_identity_claims,
        "unsafe_max_met": unsafe_record_count <= max_unsafe,
        "answer_permission_max_met": answer_permission_count <= max_answer_permission,
        "source_truth_mutation_allowed_max_met": source_truth_mutation_allowed_count <= max_source_truth_mutation_allowed,
        "write_attempt_max_met": write_attempt_count <= max_write_attempts,
    }
    quality_status = "PASS" if all(checks.values()) else "FAIL"

    summary = {
        "route_type": route_type or "",
        "citation_count": citation_count,
        "source_trace_ready_citation_count": source_trace_ready_citation_count,
        "linked_citation_count": linked_citation_count,
        "unsupported_claim_count": unsupported_claim_count,
        "llava_only_part_identity_claim_count": llava_only_part_identity_claim_count,
        "unsafe_record_count": unsafe_record_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "write_attempt_count": write_attempt_count,
        "webui_answer_ready": bool(adapter.get("webui_answer_ready")),
        "image_route_quality_gate_ready": quality_status == "PASS",
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "quality_status": quality_status,
        "route_type": ROUTE_TYPE,
        "source_adapter_status": adapter.get("status"),
        "source_adapter_quality_status": adapter.get("quality_status"),
        "summary": summary,
        "checks": checks,
        "answer": answer,
        "citations": citations,
        "safety_contract": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "llava_only_part_identity_blocked": True,
        },
    }


def check_gate(
    *,
    adapter_path: Path,
    output_path: Path,
    require_quality_pass: bool = False,
    require_webui_answer_ready: bool = False,
    min_citations: int = 0,
    min_source_trace_ready_citations: int = 0,
    max_unsupported_claims: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    adapter = _load_json(adapter_path)
    result = evaluate_gate(
        adapter,
        require_webui_answer_ready=require_webui_answer_ready,
        min_citations=min_citations,
        min_source_trace_ready_citations=min_source_trace_ready_citations,
        max_unsupported_claims=max_unsupported_claims,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    if require_quality_pass and result["quality_status"] != "PASS":
        result["quality_status"] = "FAIL"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check TRACE-Net image route multi-route quality gate v1")
    p.add_argument("--adapter", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-webui-answer-ready", action="store_true")
    p.add_argument("--min-citations", type=int, default=0)
    p.add_argument("--min-source-trace-ready-citations", type=int, default=0)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    result = check_gate(
        adapter_path=Path(args.adapter),
        output_path=Path(args.output),
        require_quality_pass=args.require_quality_pass,
        require_webui_answer_ready=args.require_webui_answer_ready,
        min_citations=args.min_citations,
        min_source_trace_ready_citations=args.min_source_trace_ready_citations,
        max_unsupported_claims=args.max_unsupported_claims,
        max_llava_only_part_identity_claims=args.max_llava_only_part_identity_claims,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = result["summary"]
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    print(f"route_type={result['route_type']}")
    print(f"citation_count={s['citation_count']}")
    print(f"source_trace_ready_citation_count={s['source_trace_ready_citation_count']}")
    print(f"linked_citation_count={s['linked_citation_count']}")
    print(f"webui_answer_ready={s['webui_answer_ready']}")
    print(f"image_route_quality_gate_ready={s['image_route_quality_gate_ready']}")
    print(f"unsupported_claim_count={s['unsupported_claim_count']}")
    print(f"llava_only_part_identity_claim_count={s['llava_only_part_identity_claim_count']}")
    print(f"unsafe_record_count={s['unsafe_record_count']}")
    print(f"answer_permission_count={s['answer_permission_count']}")
    print(f"source_truth_mutation_allowed_count={s['source_truth_mutation_allowed_count']}")
    print(f"write_attempt_count={s['write_attempt_count']}")
    print(f"gate={args.output}")
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
