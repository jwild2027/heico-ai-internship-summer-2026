#!/usr/bin/env python3
"""Filter TRACE-Net engineering LLM question-bank JSONL by question IDs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tiff.trace_net_h16d_llm_answer_reliability_v1 import filter_question_records, safety_contract_summary
except ModuleNotFoundError:  # compatible with the earlier H16C helper name
    from tiff.trace_net_h16c_llm_answer_reliability_v1 import filter_question_records, safety_contract_summary


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(obj, dict):
                raise SystemExit(f"question-bank record is not an object at {path}:{line_no}")
            records.append(obj)
    return records


def _write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--question-ids", required=True, help="Comma-separated IDs, e.g. q06,q07,q09,q18")
    ap.add_argument("--output", required=True)
    ap.add_argument("--write-manifest", action="store_true")
    args = ap.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    ids = [x.strip() for x in args.question_ids.split(",") if x.strip()]

    records = _read_jsonl(source)
    filtered = filter_question_records(records, ids)
    found_ids = {str(r.get("question_id")) for r in filtered}
    missing = [q for q in ids if q not in found_ids]
    if missing:
        raise SystemExit("missing requested question_id(s): " + ",".join(missing))

    _write_jsonl(output, filtered)

    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if args.write_manifest:
        manifest = {
            "status": "TRACE_NET_ENGINEERING_LLM_QUESTION_BANK_FILTERED",
            "quality_status": "PASS",
            "source": str(source),
            "output": str(output),
            "requested_question_ids": ids,
            "source_record_count": len(records),
            "filtered_record_count": len(filtered),
            "safety_contract": safety_contract_summary(),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print("status=TRACE_NET_ENGINEERING_LLM_QUESTION_BANK_FILTERED")
    print("quality_status=PASS")
    print(f"source_record_count={len(records)}")
    print(f"filtered_record_count={len(filtered)}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
