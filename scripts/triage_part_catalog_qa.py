#!/usr/bin/env python3
"""Triage the part catalog QA report and print a terminal summary."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# Make `python scripts/triage_part_catalog_qa.py` work from the repo root on
# Windows/Git Bash. Without this, Python only adds scripts/ to sys.path.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.part_qa_severity import (  # noqa: E402
    REVIEW_SEVERITIES,
    choose_default_input,
    count_by,
    load_qa_rows,
    summarize_triage,
    terminal_row_summary,
    triage_rows,
    write_triage_outputs,
)


def _backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".raw.bak"))


def _print_counts(title: str, counts: dict[str, int], *, limit: int = 12) -> None:
    print(title)
    if not counts:
        print("  none")
        return
    for idx, (name, count) in enumerate(counts.items()):
        if idx >= limit:
            remaining = len(counts) - limit
            print(f"  ... {remaining} more")
            break
        print(f"  {name}: {count}")


def _print_examples(title: str, rows: list[dict[str, object]], *, limit: int) -> None:
    print(title)
    if not rows:
        print("  none")
        return
    for idx, row in enumerate(rows[:limit], start=1):
        print(f"  {idx}. {terminal_row_summary(row)}")
    if len(rows) > limit:
        print(f"  ... {len(rows) - limit} more not shown")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _refresh_pipeline_manifest_qa_summary(
    *,
    qa_csv: str | Path,
    qa_json: str | Path,
    manifest_path: str | Path = "local_data/pipeline_runs/latest_backend_pipeline.json",
) -> list[Path]:
    """Refresh the QA summary inside the latest pipeline manifest.

    The QA triage command can be run after the pipeline. In that case the QA
    CSV/JSON are current, but the manifest still contains the raw QA counts from
    the older pipeline run. This helper updates only the QA-related manifest
    fields so `check_pipeline_quality.py` and `show_pipeline_status.py` agree
    with the triaged report.
    """
    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        return []

    from tiff.pipeline_manifest import summarize_qa_json  # noqa: WPS433

    manifest = _load_json(manifest_file)
    if not isinstance(manifest, dict):
        return []

    qa_json_path = Path(qa_json)
    qa_payload = _load_json(qa_json_path)
    manifest["qa_summary"] = summarize_qa_json(qa_payload)

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    artifacts["qa_csv"] = str(Path(qa_csv))
    artifacts["qa_json"] = str(qa_json_path)
    # HTML is intentionally not part of the QA triage workflow anymore.
    artifacts.pop("qa_html", None)
    manifest["artifacts"] = artifacts

    written: list[Path] = []
    _write_json(manifest_file, manifest)
    written.append(manifest_file)

    run_id = str(manifest.get("run_id") or "").strip()
    if run_id:
        timestamped = manifest_file.parent / f"tiff_backend_pipeline_{run_id}.json"
        if timestamped != manifest_file:
            _write_json(timestamped, manifest)
            written.append(timestamped)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=None,
        help="Existing QA CSV/JSON. Defaults to local_data/qa/part_catalog_qa_all.csv if present.",
    )
    parser.add_argument(
        "--output-prefix",
        default="local_data/qa/part_catalog_qa_triaged",
        help="Output prefix for optional .csv and .json triage files. HTML is not generated.",
    )
    parser.add_argument(
        "--write-files",
        action="store_true",
        help="Write optional triage .csv and .json files in addition to printing the terminal summary.",
    )
    parser.add_argument(
        "--preserve-severity",
        action="store_true",
        help="Keep the raw severity column unchanged and only add triage_severity fields.",
    )
    parser.add_argument(
        "--replace-all-report",
        action="store_true",
        help="Write triaged rows back to local_data/qa/part_catalog_qa_all.csv/.json after backing up existing files.",
    )
    parser.add_argument(
        "--no-refresh-manifest",
        action="store_true",
        help="Do not refresh latest_backend_pipeline.json after --replace-all-report.",
    )
    parser.add_argument(
        "--show",
        choices=("review", "suppressed", "all"),
        default="review",
        help="Which example rows to print after the summary.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum number of example rows to print.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input) if args.input else choose_default_input()
    raw_rows = load_qa_rows(input_path)
    rows = triage_rows(raw_rows, replace_severity=not args.preserve_severity)
    summary = summarize_triage(rows)

    review_rows = [row for row in rows if str(row.get("severity", "")).lower() in REVIEW_SEVERITIES]
    suppressed_rows = [row for row in rows if str(row.get("triage_action", "")).lower() == "suppress_from_review_queue"]

    print("Part catalog QA triage")
    print(f"  Input: {input_path}")
    print(f"  Input rows: {len(raw_rows)}")
    print(f"  Review queue rows after triage: {summary['review_queue_rows']}")
    print(f"  Suppressed from review queue: {summary['suppressed_from_review_queue']}")
    print("")
    _print_counts("By severity:", summary["by_severity"])
    print("")
    _print_counts("By triage action:", summary["by_triage_action"])
    print("")
    _print_counts("Top triage categories:", count_by(rows, "triage_category"))
    print("")

    if args.show == "review":
        _print_examples("Rows still needing review:", review_rows, limit=max(args.limit, 0))
    elif args.show == "suppressed":
        _print_examples("Rows suppressed from review:", suppressed_rows, limit=max(args.limit, 0))
    else:
        _print_examples("Triaged rows:", rows, limit=max(args.limit, 0))

    wrote_any = False
    if args.write_files:
        outputs = write_triage_outputs(rows, args.output_prefix)
        print("")
        print("Wrote triage files:")
        print(f"  CSV: {outputs['csv']}")
        print(f"  JSON: {outputs['json']}")
        wrote_any = True

    if args.replace_all_report:
        all_prefix = Path("local_data/qa/part_catalog_qa_all")
        for suffix in (".csv", ".json"):
            _backup(all_prefix.with_suffix(suffix))
        outputs = write_triage_outputs(rows, all_prefix)
        print("")
        print("Replaced normal QA report after writing .raw.bak backups:")
        print(f"  CSV: {outputs['csv']}")
        print(f"  JSON: {outputs['json']}")
        wrote_any = True

        if not args.no_refresh_manifest:
            try:
                updated = _refresh_pipeline_manifest_qa_summary(
                    qa_csv=outputs["csv"],
                    qa_json=outputs["json"],
                )
            except Exception as exc:  # pragma: no cover - defensive CLI path
                print(f"Warning: could not refresh pipeline manifest QA summary: {exc}", file=sys.stderr)
            else:
                if updated:
                    print("Refreshed pipeline manifest QA summary:")
                    for path in updated:
                        print(f"  {path}")

    if not wrote_any:
        print("")
        print("No files written. Use --write-files for CSV/JSON or --replace-all-report to update the normal QA report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
