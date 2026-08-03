"""Quality gate for TRACE-Net Page Context v2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CONTEXT_V2 = Path("local_data/organization/context/page_contexts_v2.json")
DEFAULT_QUALITY = Path("local_data/organization/context/page_contexts_v2_quality.json")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def normalize(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, dict) and isinstance(raw.get("contexts"), list):
        return [r for r in raw["contexts"] if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        return [dict(v, page_id=k) for k, v in raw.items() if isinstance(v, dict)]
    return []


def run_quality(records: List[Dict[str, Any]], thresholds: Dict[str, int]) -> Dict[str, Any]:
    summary = {
        "context_records": len(records),
        "contexts_with_retrieval_cues": sum(1 for r in records if r.get("retrieval_cues")),
        "contexts_with_answerable_questions": sum(1 for r in records if r.get("answerable_questions")),
        "contexts_with_supporting_ocr_phrases": sum(1 for r in records if r.get("supporting_ocr_phrases")),
        "blank_context_records": sum(1 for r in records if r.get("role") == "blank"),
        "direct_answer_context_records": sum(1 for r in records if r.get("authority", {}).get("can_answer_directly")),
        "canonical_source_truth_context_records": sum(1 for r in records if r.get("authority", {}).get("canonical_source_truth")),
        "source_truth_mutation_records": sum(1 for r in records if r.get("authority", {}).get("source_truth_mutation_allowed")),
        "missing_authority_records": sum(1 for r in records if not isinstance(r.get("authority"), dict)),
        "missing_page_id_records": sum(1 for r in records if not r.get("page_id")),
    }
    checks = []
    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    check("context_records", summary["context_records"] >= thresholds.get("min_context_records", 0), f"contexts={summary['context_records']}; minimum={thresholds.get('min_context_records', 0)}")
    check("retrieval_cues", summary["contexts_with_retrieval_cues"] >= thresholds.get("min_contexts_with_retrieval_cues", 0), f"with_cues={summary['contexts_with_retrieval_cues']}; minimum={thresholds.get('min_contexts_with_retrieval_cues', 0)}")
    check("answerable_questions", summary["contexts_with_answerable_questions"] >= thresholds.get("min_contexts_with_answerable_questions", 0), f"with_questions={summary['contexts_with_answerable_questions']}; minimum={thresholds.get('min_contexts_with_answerable_questions', 0)}")
    check("supporting_ocr", summary["contexts_with_supporting_ocr_phrases"] >= thresholds.get("min_contexts_with_supporting_ocr_phrases", 0), f"with_ocr_phrases={summary['contexts_with_supporting_ocr_phrases']}; minimum={thresholds.get('min_contexts_with_supporting_ocr_phrases', 0)}")
    check("direct_answer_blocked", summary["direct_answer_context_records"] <= thresholds.get("max_direct_answer_context_records", 0), f"direct_answer={summary['direct_answer_context_records']}; max={thresholds.get('max_direct_answer_context_records', 0)}")
    check("canonical_source_truth_blocked", summary["canonical_source_truth_context_records"] <= thresholds.get("max_canonical_source_truth_context_records", 0), f"canonical={summary['canonical_source_truth_context_records']}; max={thresholds.get('max_canonical_source_truth_context_records', 0)}")
    check("source_truth_mutation_blocked", summary["source_truth_mutation_records"] <= thresholds.get("max_source_truth_mutations", 0), f"mutations={summary['source_truth_mutation_records']}; max={thresholds.get('max_source_truth_mutations', 0)}")
    check("authority_present", summary["missing_authority_records"] <= thresholds.get("max_missing_authority_records", 0), f"missing_authority={summary['missing_authority_records']}; max={thresholds.get('max_missing_authority_records', 0)}")
    check("page_ids_present", summary["missing_page_id_records"] <= thresholds.get("max_missing_page_id_records", 0), f"missing_page_id={summary['missing_page_id_records']}; max={thresholds.get('max_missing_page_id_records', 0)}")
    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    return {"status": status, "summary": summary, "checks": checks}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Page Context v2 quality.")
    parser.add_argument("--context-file", default=str(DEFAULT_CONTEXT_V2))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--min-context-records", type=int, default=1)
    parser.add_argument("--min-contexts-with-retrieval-cues", type=int, default=0)
    parser.add_argument("--min-contexts-with-answerable-questions", type=int, default=0)
    parser.add_argument("--min-contexts-with-supporting-ocr-phrases", type=int, default=0)
    parser.add_argument("--max-direct-answer-context-records", type=int, default=0)
    parser.add_argument("--max-canonical-source-truth-context-records", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    parser.add_argument("--max-missing-authority-records", type=int, default=0)
    parser.add_argument("--max-missing-page-id-records", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    raw = read_json(Path(args.context_file))
    records = normalize(raw)
    thresholds = vars(args)
    report = run_quality(records, thresholds)
    print("TRACE-Net Page Context v2 quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for k, v in report["summary"].items():
        print(f"    {k}: {v}")
    print("  Checks:")
    for c in report["checks"]:
        print(f"    {'OK' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}")
    if args.write_json:
        Path(args.quality).parent.mkdir(parents=True, exist_ok=True)
        Path(args.quality).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON: {args.quality}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
