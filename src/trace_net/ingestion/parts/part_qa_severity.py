"""Post-process part-catalog QA rows into cleaner severity buckets.

The existing QA report is intentionally conservative, so a lot of harmless OCR
noise can land in ``review``. This module keeps the raw finding, preserves its
original severity, and adds triage fields that separate real catalog issues from
non-part references and informational rows.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REVIEW_SEVERITIES = {"review", "error"}
SUPPRESSED_STATES = {
    "ignored",
    "ignore",
    "suppressed",
    "suppress",
    "false_positive",
    "not_a_part",
    "non_part",
    "resolved",
}
NOISE_TOKENS = {
    "FIGURE",
    "IGURE",
    "SHEET",
    "PER STOCK",
    "PER",
    "STOCK",
    "ITEM",
    "QTY",
    "EFF",
    "CODE",
    "UNITS",
    "REF",
    "REPL",
    "IPL",
    "IPC",
    "TP",
    "T.P",
    "T.P.",
    "NHA",
}
PART_TOKEN_RE = re.compile(r"\b[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8}){1,5}\b", re.I)
ATA_REF_RE = re.compile(r"^\d{2}-\d{2}-\d{2}(?:-\d{1,4})?$")
ATA_SHORT_REF_RE = re.compile(r"^\d{2}-(?:IPL|IPC|MM|CMM|AMM)$", re.I)
DASHED_TOKEN_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
FIGURE_OR_SHEET_REF_RE = re.compile(r"^00-\d{2}[A-Z]?$", re.I)
SLASH_PART_SEGMENT_RE = re.compile(r"^[A-Z0-9-]+$")


@dataclass(frozen=True)
class TriageDecision:
    severity: str
    category: str
    action: str
    reason: str
    part_candidate: str = ""
    issue_type: str = ""

    @property
    def needs_review(self) -> bool:
        return self.severity in REVIEW_SEVERITIES


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _get(row: Mapping[str, Any], *names: str) -> str:
    wanted = {_norm_key(name) for name in names}
    for key, value in row.items():
        if _norm_key(key) in wanted:
            return "" if value is None else str(value).strip()
    return ""


def _first(row: Mapping[str, Any], names: Sequence[str]) -> str:
    for name in names:
        value = _get(row, name)
        if value:
            return value
    return ""


def _row_text(row: Mapping[str, Any]) -> str:
    return " ".join(str(value) for value in row.values() if value is not None)


def normalize_issue_type(row: Mapping[str, Any]) -> str:
    value = _first(
        row,
        (
            "issue_type",
            "check",
            "qa_check",
            "category",
            "rule",
            "source_check",
            "finding_type",
            "type",
        ),
    )
    value = value.strip().lower()
    if value in {"", "-", "--", "n/a", "na", "none", "unknown"}:
        return ""
    value = value.replace(" ", "_").replace("-", "_")
    return re.sub(r"_+", "_", value).strip("_")


def normalize_original_severity(row: Mapping[str, Any]) -> str:
    value = _first(row, ("severity", "original_severity", "level", "status"))
    value = value.strip().lower().replace("manual_review", "review")
    if value in {"ok", "info", "review", "error"}:
        return value
    if value in {"pass", "passed", "clean"}:
        return "ok"
    if value in {"warn", "warning", "needs_review"}:
        return "review"
    if value in {"fail", "failed", "fatal"}:
        return "error"
    return "review"


def normalize_review_state(row: Mapping[str, Any]) -> str:
    value = _first(
        row,
        (
            "review_state",
            "review_status",
            "triage_state",
            "qa_state",
            "resolution",
            "disposition",
        ),
    )
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def normalize_part_candidate(value: Any) -> str:
    text = "" if value is None else str(value).strip().upper()
    for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014"):
        text = text.replace(dash, "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,:;()[]{}<>|/\\")


def extract_part_candidate(row: Mapping[str, Any]) -> str:
    direct = _first(
        row,
        (
            "part_number",
            "part",
            "normalized_part",
            "candidate_part",
            "part_candidate",
            "token",
            "value",
            "pn",
        ),
    )
    if direct:
        return normalize_part_candidate(direct)
    match = PART_TOKEN_RE.search(_row_text(row))
    return normalize_part_candidate(match.group(0)) if match else ""


def looks_like_ata_reference(part: str) -> bool:
    candidate = normalize_part_candidate(part)
    return bool(candidate and (ATA_REF_RE.match(candidate) or ATA_SHORT_REF_RE.match(candidate)))


def looks_like_doc_reference(part: str) -> bool:
    candidate = normalize_part_candidate(part)
    if candidate in NOISE_TOKENS:
        return True
    compact = re.sub(r"[^A-Z0-9]", "", candidate)
    noise_compact = {re.sub(r"[^A-Z0-9]", "", token) for token in NOISE_TOKENS}
    return compact in noise_compact


def looks_like_figure_or_sheet_reference(part: str) -> bool:
    """Return True for figure/sheet/index codes that are not catalog parts."""
    candidate = normalize_part_candidate(part)
    return bool(candidate and FIGURE_OR_SHEET_REF_RE.match(candidate))


def looks_like_compound_part_reference(part: str) -> bool:
    """Return True for slash-separated part groups/ranges.

    Examples from the QA output include ``120-29067-019/029`` and
    ``120-29068-017/027/039/059``. These are useful source references, but
    they are not a single canonical part-number row, so they should be kept as
    info instead of manual-review conflicts.
    """
    candidate = normalize_part_candidate(part)
    if "/" not in candidate:
        return False
    segments = [segment.strip() for segment in candidate.split("/") if segment.strip()]
    if len(segments) < 2:
        return False
    if not all(SLASH_PART_SEGMENT_RE.match(segment) for segment in segments):
        return False
    has_digit = any(re.search(r"\d", segment) for segment in segments)
    has_dash = any("-" in segment for segment in segments)
    all_numeric_suffixes = all(bool(re.match(r"^\d{2,6}[A-Z]?$", segment)) for segment in segments)
    # E0/5221 is a slash code, but it is not shaped like a part group.
    if not has_digit:
        return False
    return has_dash or all_numeric_suffixes


def looks_like_slash_nonpart_reference(part: str) -> bool:
    candidate = normalize_part_candidate(part)
    return "/" in candidate and not looks_like_compound_part_reference(candidate)


def looks_like_ocr_noise(part: str) -> bool:
    candidate = normalize_part_candidate(part)
    if not candidate:
        return False
    compact = re.sub(r"[^A-Z0-9]", "", candidate)
    if not compact:
        return True
    if looks_like_doc_reference(candidate):
        return True
    if len(compact) <= 2 and not any(ch.isdigit() for ch in compact):
        return True
    return False


def looks_like_plausible_part(part: str) -> bool:
    candidate = normalize_part_candidate(part)
    if not candidate:
        return False
    if "/" in candidate:
        return False
    if looks_like_ata_reference(candidate) or looks_like_doc_reference(candidate):
        return False
    if looks_like_figure_or_sheet_reference(candidate):
        return False
    if "-" in candidate:
        return len(candidate) >= 5 and bool(DASHED_TOKEN_RE.match(candidate))
    has_alpha = bool(re.search(r"[A-Z]", candidate))
    has_digit = bool(re.search(r"\d", candidate))
    return has_alpha and has_digit and 5 <= len(candidate) <= 24


def _mentions(row: Mapping[str, Any], *needles: str) -> bool:
    text = _row_text(row).lower()
    return any(needle.lower() in text for needle in needles)


def _nomenclature_has_ocr_noise(row: Mapping[str, Any]) -> bool:
    value = _first(row, ("nomenclature", "canonical_nomenclature", "raw_nomenclature", "name", "description")).upper()
    if not value:
        return False
    return any(token in value for token in ("........", "EEEE", "0000", "VWS", "VES"))


def triage_row(row: Mapping[str, Any]) -> TriageDecision:
    original = normalize_original_severity(row)
    issue_type = normalize_issue_type(row)
    review_state = normalize_review_state(row)
    part = extract_part_candidate(row)

    if review_state in SUPPRESSED_STATES:
        return TriageDecision("info", "reviewed_suppressed", "suppress_from_review_queue", f"review_state is {review_state}", part, issue_type)

    if original == "ok":
        return TriageDecision("ok", "ok", "keep", "row is already marked ok", part, issue_type)

    if part and looks_like_ata_reference(part):
        return TriageDecision("info", "non_part_ata_reference", "suppress_from_review_queue", "candidate looks like an ATA/chapter/page reference, not a part number", part, issue_type)

    if part and looks_like_figure_or_sheet_reference(part):
        return TriageDecision("info", "non_part_figure_or_sheet_reference", "suppress_from_review_queue", "candidate looks like a figure/sheet/index code, not a catalog part number", part, issue_type)

    if part and looks_like_compound_part_reference(part):
        return TriageDecision("info", "compound_part_reference", "keep_as_info", "candidate is a slash-separated part group/range, not one canonical catalog part row", part, issue_type)

    if part and looks_like_slash_nonpart_reference(part):
        return TriageDecision("info", "non_part_slash_reference", "suppress_from_review_queue", "slash-separated code does not look like a part-number group", part, issue_type)

    if part and looks_like_ocr_noise(part):
        return TriageDecision("info", "ocr_or_document_noise", "suppress_from_review_queue", "candidate is a known OCR/document token rather than a part number", part, issue_type)

    if _nomenclature_has_ocr_noise(row):
        return TriageDecision("info", "nomenclature_ocr_noise", "suppress_from_review_queue", "nomenclature text contains OCR decoration/noise markers", part, issue_type)

    if "suspicious_part_ata" in issue_type:
        if part and looks_like_plausible_part(part):
            return TriageDecision("review", "plausible_part_flagged_as_ata_like", "manual_review", "candidate looks like a real part even though the ATA rule flagged it", part, issue_type)
        return TriageDecision("info", "non_part_ata_reference", "suppress_from_review_queue", "suspicious ATA finding does not look like a real part number", part, issue_type)

    if "nomenclature_group" in issue_type:
        return TriageDecision("info", "informational_nomenclature_group", "keep_as_info", "many real parts can share the same nomenclature, so this is informational by default", part, issue_type)

    if "missing_nomenclature" in issue_type or _mentions(row, "missing nomenclature"):
        if part and looks_like_plausible_part(part):
            return TriageDecision("review", "real_part_missing_nomenclature", "manual_review", "candidate looks like a real part with missing nomenclature", part, issue_type)
        return TriageDecision("info", "non_part_missing_nomenclature_noise", "suppress_from_review_queue", "missing-nomenclature row does not contain a plausible part number", part, issue_type)

    if "conflict" in issue_type or _mentions(row, "conflict", "conflicting nomenclature"):
        if part and looks_like_plausible_part(part):
            return TriageDecision("review", "real_part_nomenclature_conflict", "manual_review", "candidate looks like a real part with conflicting nomenclature evidence", part, issue_type)
        return TriageDecision("info", "non_part_conflict_noise", "suppress_from_review_queue", "conflict row does not contain a plausible part number", part, issue_type)

    if part and not looks_like_plausible_part(part) and original in REVIEW_SEVERITIES:
        return TriageDecision("info", "non_part_reference_or_noise", "suppress_from_review_queue", "review row does not contain a plausible part number", part, issue_type)

    if part and looks_like_plausible_part(part) and original in REVIEW_SEVERITIES:
        return TriageDecision("review", "real_part_catalog_review", "manual_review", "candidate looks like a real part; keep in review even though no specific QA rule matched", part, issue_type)

    if original == "error":
        return TriageDecision("error", "unclassified_error", "manual_review", "raw QA row was already an error and no noise rule matched", part, issue_type)
    if original == "info":
        return TriageDecision("info", "info", "keep_as_info", "raw QA row was already informational and no stronger rule matched", part, issue_type)
    return TriageDecision("review", "unclassified_review", "manual_review", "no noise/suppression rule matched", part, issue_type)


def triage_rows(rows: Iterable[Mapping[str, Any]], *, replace_severity: bool = True) -> list[dict[str, Any]]:
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        output = dict(row)
        original = normalize_original_severity(output)
        decision = triage_row(output)
        output.setdefault("original_severity", original)
        output["triage_severity"] = decision.severity
        output["triage_category"] = decision.category
        output["triage_action"] = decision.action
        output["triage_reason"] = decision.reason
        output["triage_part_candidate"] = decision.part_candidate
        output["triage_issue_type"] = decision.issue_type
        output["needs_review"] = "true" if decision.needs_review else "false"
        if replace_severity:
            output["severity"] = decision.severity
        output_rows.append(output)
    return output_rows


def summarize_triage(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    row_list = list(rows)
    by_severity = Counter(str(row.get("severity", "")).lower() for row in row_list)
    by_original = Counter(str(row.get("original_severity", "")).lower() for row in row_list)
    by_category = Counter(str(row.get("triage_category", "")).lower() for row in row_list)
    by_action = Counter(str(row.get("triage_action", "")).lower() for row in row_list)
    return {
        "total_rows": len(row_list),
        "review_queue_rows": sum(1 for row in row_list if str(row.get("severity", "")).lower() in REVIEW_SEVERITIES),
        "suppressed_from_review_queue": sum(1 for row in row_list if str(row.get("triage_action", "")).lower() == "suppress_from_review_queue"),
        "by_severity": dict(sorted(by_severity.items())),
        "by_original_severity": dict(sorted(by_original.items())),
        "by_triage_category": dict(sorted(by_category.items())),
        "by_triage_action": dict(sorted(by_action.items())),
    }


def load_qa_rows(path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"QA report not found: {input_path}")
    if input_path.suffix.lower() == ".json":
        data = json.loads(input_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, Mapping)]
        if isinstance(data, dict):
            for key in ("rows", "findings", "items", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return [dict(row) for row in value if isinstance(row, Mapping)]
        raise ValueError(f"Could not find QA rows in JSON file: {input_path}")
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _fieldnames(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    preferred = [
        "severity",
        "original_severity",
        "triage_severity",
        "triage_category",
        "triage_action",
        "triage_reason",
        "needs_review",
        "triage_part_candidate",
        "triage_issue_type",
    ]
    seen: set[str] = set()
    names: list[str] = []
    for name in preferred:
        if any(name in row for row in rows):
            names.append(name)
            seen.add(name)
    for row in rows:
        for name in row:
            if name not in seen:
                names.append(str(name))
                seen.add(str(name))
    return names


def write_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    names = _fieldnames(rows) if rows else []
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def write_json(rows: Sequence[Mapping[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summarize_triage(rows), "rows": [dict(row) for row in rows]}
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def choose_default_input(base_dir: str | Path = "local_data/qa") -> Path:
    base = Path(base_dir)
    csv_path = base / "part_catalog_qa_all.csv"
    json_path = base / "part_catalog_qa_all.json"
    if csv_path.exists():
        return csv_path
    if json_path.exists():
        return json_path
    return csv_path


def write_triage_outputs(rows: Sequence[Mapping[str, Any]], output_prefix: str | Path) -> dict[str, str]:
    """Write machine-readable triage files.

    HTML is intentionally not generated here. The command-line script prints the
    human-readable report directly to the terminal.
    """
    prefix = Path(output_prefix)
    outputs = {
        "csv": str(prefix.with_suffix(".csv")),
        "json": str(prefix.with_suffix(".json")),
    }
    write_csv(rows, outputs["csv"])
    write_json(rows, outputs["json"])
    return outputs


def count_by(rows: Iterable[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row.get(field, "")).strip() or "<blank>" for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def terminal_row_summary(row: Mapping[str, Any]) -> str:
    part = row.get("triage_part_candidate") or row.get("part_number") or row.get("part") or ""
    issue = row.get("triage_issue_type") or row.get("issue_type") or row.get("check") or ""
    category = row.get("triage_category") or ""
    severity = row.get("severity") or row.get("triage_severity") or ""
    reason = row.get("triage_reason") or ""
    message = row.get("message") or row.get("nomenclature") or row.get("description") or ""
    pieces = [
        f"severity={severity}",
        f"part={part or '-'}",
        f"issue={issue or '-'}",
        f"category={category or '-'}",
    ]
    if reason:
        pieces.append(f"reason={reason}")
    if message:
        text = str(message).replace("\n", " ").strip()
        if len(text) > 120:
            text = text[:117].rstrip() + "..."
        pieces.append(f"message={text}")
    return " | ".join(pieces)
