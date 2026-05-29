#!/usr/bin/env python
"""Check local TIFF API backend readiness without starting FastAPI."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.api_backend import api_status, part_lookup, page_lookup, trace_vector_payload  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", default="120-37313-001")
    parser.add_argument("--page", default="t_p_120_1176_p000083")
    parser.add_argument("--vector-page", default="t_p_120_1176_p000495")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/api/tiff_api_ready.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status = api_status()
    part = part_lookup(args.part, limit=3)
    page = page_lookup(args.page, limit=3)
    vector = trace_vector_payload(args.vector_page, chunk_id=f"chunk_{args.vector_page}_001", score=0.5, limit=3)

    ready = (
        str(status.get("status", "")).lower() == "ok"
        and part.get("status") == "ok"
        and page.get("status") == "ok"
        and vector.get("status") == "OK"
    )
    report = {
        "status": "OK" if ready else "NEEDS ATTENTION",
        "api_status": status,
        "part_probe": {
            "part_number": args.part,
            "status": part.get("status"),
            "pages_total": part.get("pages_total"),
            "nomenclature": part.get("nomenclature"),
        },
        "page_probe": {
            "page_id": args.page,
            "status": page.get("status"),
            "source_link_present": (page.get("page") or {}).get("source_link_present"),
            "context_present": (page.get("page") or {}).get("context_present"),
        },
        "vector_trace_probe": {
            "page_id": args.vector_page,
            "status": vector.get("status"),
        },
        "suggested_server_command": "python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000",
    }

    print("TIFF API readiness")
    print(f"  Status: {report['status']}")
    print(f"  Backend quality: {status.get('status')}")
    print(f"  Graph nodes: {(status.get('graph') or {}).get('nodes_total')}")
    print(f"  Page contexts: {(status.get('graph') or {}).get('page_context_nodes')}")
    print(f"  Source links: {(status.get('graph') or {}).get('source_link_nodes')}")
    print(f"  Part probe: {args.part} | {part.get('status')} | pages={part.get('pages_total')} | name={part.get('nomenclature')}")
    print(f"  Page probe: {args.page} | {page.get('status')} | source={(page.get('page') or {}).get('source_link_present')} | context={(page.get('page') or {}).get('context_present')}")
    print(f"  Vector trace probe: {args.vector_page} | {vector.get('status')}")
    print("  Server command:")
    print(f"    {report['suggested_server_command']}")

    if args.write_json:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  JSON: {output}")

    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
