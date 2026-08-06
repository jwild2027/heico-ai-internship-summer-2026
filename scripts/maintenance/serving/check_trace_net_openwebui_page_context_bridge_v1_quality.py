from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE = "check_trace_net_openwebui_page_context_bridge_v1_quality"


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def check_quality(manifest: Mapping[str, Any], *, require_page_context_used: bool = True, min_pages: int = 1) -> dict[str, Any]:
    failures: list[str] = []
    meta = manifest.get("bridge_meta") if isinstance(manifest.get("bridge_meta"), Mapping) else {}
    summary = meta.get("context_pack_summary") if isinstance(meta.get("context_pack_summary"), Mapping) else {}

    if require_page_context_used and not meta.get("page_context_used"):
        failures.append("page_context_not_used")
    if meta.get("context_pack_quality_status") not in ("PASS", None):
        failures.append("context_pack_quality_not_pass")
    if _as_int(summary.get("selected_page_count")) < min_pages:
        failures.append(f"selected_page_count_lt_{min_pages}")
    if _as_int(summary.get("answer_permission_count")) != 0:
        failures.append("answer_permission_count_nonzero")
    if _as_int(summary.get("source_truth_mutation_allowed_count")) != 0:
        failures.append("source_truth_mutation_allowed_count_nonzero")
    if _as_int(summary.get("postgres_write_attempt_count")) != 0:
        failures.append("postgres_write_attempt_count_nonzero")
    if _as_int(summary.get("qdrant_write_attempt_count")) != 0:
        failures.append("qdrant_write_attempt_count_nonzero")
    if _as_int(summary.get("opensearch_write_attempt_count")) != 0:
        failures.append("opensearch_write_attempt_count_nonzero")

    messages = manifest.get("enriched_messages_preview") if isinstance(manifest.get("enriched_messages_preview"), list) else []
    rendered = json.dumps(messages, ensure_ascii=False)
    if "TRACE-NET PAGE CONTEXT BINDER V3" not in rendered:
        failures.append("binder_preview_missing")
    if "model_should_think" not in rendered:
        failures.append("reasoning_work_order_missing_from_preview")

    return {
        "module": MODULE,
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "summary": {
            "page_context_used": bool(meta.get("page_context_used")),
            "context_pack_quality_status": meta.get("context_pack_quality_status"),
            "selected_page_count": _as_int(summary.get("selected_page_count")),
            "proof_record_count": _as_int(summary.get("proof_record_count")),
            "guidance_record_count": _as_int(summary.get("guidance_record_count")),
            "answer_permission_count": _as_int(summary.get("answer_permission_count")),
            "source_truth_mutation_allowed_count": _as_int(summary.get("source_truth_mutation_allowed_count")),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=MODULE)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--allow-no-page-context", action="store_true")
    args = parser.parse_args(argv)

    inp = Path(args.input)
    manifest = json.loads(inp.read_text(encoding="utf-8"))
    result = check_quality(
        manifest,
        require_page_context_used=not args.allow_no_page_context,
        min_pages=args.min_pages,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote: {out}")
    print("quality_status:", result["quality_status"])
    print("failure_reasons:", result["failure_reasons"])
    print("summary:", result["summary"])
    return 0 if result["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
