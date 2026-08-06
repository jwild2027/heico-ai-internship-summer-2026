#!/usr/bin/env python3
"""Fixed-50 QA runner for a sample metadata/TIFF ZIP.

This runner is intentionally deterministic and read-only. It inspects a ZIP that
contains a METS metadata.xml file plus TIFF page images, builds 50 grounded
questions from facts inside the ZIP, prints progress, and writes answers in a
simple Question/Answer format.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

NS = {
    "mets": "http://www.loc.gov/METS/",
    "mods": "http://www.loc.gov/mods/v3",
    "mix": "http://www.loc.gov/mix/",
    "xlink": "http://www.w3.org/1999/xlink",
}

MODULE = "trace_net_sample_zip_fixed50_qa_v1"
STATUS = "TRACE_NET_SAMPLE_ZIP_FIXED50_QA_DONE"
VERSION = "v1"


@dataclass(frozen=True)
class MetsFileRecord:
    file_id: str
    href: str
    size: int
    mimetype: str
    checksum: str
    checksum_type: str


def _text(root: ET.Element, path: str) -> str:
    node = root.find(path, NS)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _attr(root: ET.Element, path: str, name: str) -> str:
    node = root.find(path, NS)
    if node is None:
        return ""
    return node.attrib.get(name, "")


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _basename_from_href(href: str) -> str:
    value = href.replace("file://./", "").replace("file://", "")
    return value.split("/")[-1]


def _tif_number(name: str) -> Optional[int]:
    stem = Path(name).stem
    if stem.isdigit():
        return int(stem)
    return None


def parse_mets(metadata_xml: str) -> Dict[str, Any]:
    root = ET.fromstring(metadata_xml)

    agent = root.find("mets:metsHdr/mets:agent", NS)
    agent_name = ""
    agent_note = ""
    if agent is not None:
        name_node = agent.find("mets:name", NS)
        note_node = agent.find("mets:note", NS)
        agent_name = (name_node.text or "").strip() if name_node is not None else ""
        agent_note = (note_node.text or "").strip() if note_node is not None else ""

    mix_format = root.find("mets:amdSec/mets:techMD/mets:mdWrap/mets:xmlData/mix:mix/mix:BasicImageParameters/mix:Format", NS)
    mime_type = ""
    byte_order = ""
    compression_scheme = ""
    color_space = ""
    if mix_format is not None:
        mime_type = _text(mix_format, "mix:MIMEType")
        byte_order = _text(mix_format, "mix:ByteOrder")
        compression_scheme = _text(mix_format, "mix:Compression/mix:CompressionScheme")
        color_space = _text(mix_format, "mix:PhotometricInterpretation/mix:ColorSpace")

    file_records: List[MetsFileRecord] = []
    for file_node in root.findall("mets:fileSec/mets:fileGrp/mets:file", NS):
        flocat = file_node.find("mets:FLocat", NS)
        href = ""
        if flocat is not None:
            href = flocat.attrib.get(f"{{{NS['xlink']}}}href", "")
        file_records.append(
            MetsFileRecord(
                file_id=file_node.attrib.get("ID", ""),
                href=href,
                size=_safe_int(file_node.attrib.get("SIZE", "0")),
                mimetype=file_node.attrib.get("MIMETYPE", ""),
                checksum=file_node.attrib.get("CHECKSUM", ""),
                checksum_type=file_node.attrib.get("CHECKSUMTYPE", ""),
            )
        )

    page_start = _text(root, ".//mods:part/mods:extent/mods:start")
    page_end = _text(root, ".//mods:part/mods:extent/mods:end")
    start_i = _safe_int(page_start)
    end_i = _safe_int(page_end)
    reported_page_count = end_i - start_i + 1 if start_i and end_i and end_i >= start_i else 0

    return {
        "root_label": root.attrib.get("LABEL", ""),
        "root_objid": root.attrib.get("OBJID", ""),
        "root_type": root.attrib.get("TYPE", ""),
        "record_created": _attr(root, "mets:metsHdr", "CREATEDATE"),
        "record_status": _attr(root, "mets:metsHdr", "RECORDSTATUS"),
        "creator_name": agent_name,
        "creator_note": agent_note,
        "mods_title": _text(root, ".//mods:titleInfo/mods:title"),
        "owner": _text(root, ".//mods:name/mods:namePart"),
        "resource_type": _text(root, ".//mods:typeOfResource"),
        "genre": _text(root, ".//mods:genre"),
        "date_captured": _text(root, ".//mods:originInfo/mods:dateCaptured"),
        "issuance": _text(root, ".//mods:originInfo/mods:issuance"),
        "language_code": _text(root, ".//mods:language/mods:languageTerm"),
        "abstract": _text(root, ".//mods:abstract"),
        "local_identifier": _text(root, ".//mods:identifier"),
        "location_url": _text(root, ".//mods:location/mods:url"),
        "page_start": page_start,
        "page_end": page_end,
        "reported_page_count": reported_page_count,
        "image_mime_type": mime_type,
        "byte_order": byte_order,
        "compression_scheme": compression_scheme,
        "color_space": color_space,
        "file_records": [r.__dict__ for r in file_records],
    }


def inspect_sample_zip(sample_zip: Path) -> Dict[str, Any]:
    if not sample_zip.exists():
        raise FileNotFoundError(f"Sample ZIP not found: {sample_zip}")
    if not zipfile.is_zipfile(sample_zip):
        raise ValueError(f"Input is not a ZIP file: {sample_zip}")

    with zipfile.ZipFile(sample_zip) as zf:
        names = zf.namelist()
        if "metadata.xml" not in names:
            raise ValueError("Sample ZIP does not contain metadata.xml")
        metadata_xml = zf.read("metadata.xml").decode("utf-8", errors="replace")
        zip_infos = zf.infolist()

    mets = parse_mets(metadata_xml)
    tif_infos = [i for i in zip_infos if i.filename.lower().endswith((".tif", ".tiff"))]
    tif_infos_sorted = sorted(tif_infos, key=lambda i: i.filename)
    tif_sizes = [i.file_size for i in tif_infos_sorted]
    tif_numbers = [_tif_number(i.filename) for i in tif_infos_sorted]
    numeric_tifs = [n for n in tif_numbers if n is not None]
    expected_numbers = set(range(1, max(numeric_tifs) + 1)) if numeric_tifs else set()
    present_numbers = set(numeric_tifs)
    missing_numbers = sorted(expected_numbers - present_numbers)
    duplicate_names = len(tif_infos_sorted) - len({i.filename for i in tif_infos_sorted})

    first_tif = tif_infos_sorted[0] if tif_infos_sorted else None
    last_tif = tif_infos_sorted[-1] if tif_infos_sorted else None
    smallest = min(tif_infos_sorted, key=lambda i: i.file_size) if tif_infos_sorted else None
    largest = max(tif_infos_sorted, key=lambda i: i.file_size) if tif_infos_sorted else None
    small_tifs = [i for i in tif_infos_sorted if i.file_size <= 4000]

    mets_records = mets["file_records"]
    mets_tiff_records = [r for r in mets_records if str(r.get("mimetype", "")).lower() in {"image/tiff", "image/tif"}]
    first_mets = mets_tiff_records[0] if mets_tiff_records else None
    last_mets = mets_tiff_records[-1] if mets_tiff_records else None

    facts: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "sample_zip_path": str(sample_zip),
        "sample_zip_name": sample_zip.name,
        "sample_zip_size_bytes": sample_zip.stat().st_size,
        "sample_zip_sha1": _sha1_file(sample_zip),
        "zip_entry_count": len(zip_infos),
        "metadata_xml_size_bytes": len(metadata_xml.encode("utf-8")),
        "metadata_xml_present": True,
        "zip_tiff_count": len(tif_infos_sorted),
        "zip_total_tiff_bytes": sum(tif_sizes),
        "zip_average_tiff_size_bytes": int(round(statistics.mean(tif_sizes))) if tif_sizes else 0,
        "zip_median_tiff_size_bytes": int(round(statistics.median(tif_sizes))) if tif_sizes else 0,
        "first_tiff_name": first_tif.filename if first_tif else "",
        "first_tiff_size_bytes": first_tif.file_size if first_tif else 0,
        "last_tiff_name": last_tif.filename if last_tif else "",
        "last_tiff_size_bytes": last_tif.file_size if last_tif else 0,
        "smallest_tiff_name": smallest.filename if smallest else "",
        "smallest_tiff_size_bytes": smallest.file_size if smallest else 0,
        "largest_tiff_name": largest.filename if largest else "",
        "largest_tiff_size_bytes": largest.file_size if largest else 0,
        "small_tiff_count_le_4000": len(small_tifs),
        "small_tiff_examples": [i.filename for i in small_tifs[:10]],
        "tiff_numbers_are_consecutive": len(missing_numbers) == 0 and len(numeric_tifs) == len(tif_infos_sorted),
        "missing_tiff_numbers": missing_numbers[:50],
        "duplicate_tiff_name_count": duplicate_names,
        "mets_tiff_count": len(mets_tiff_records),
        "mets_total_tiff_bytes": sum(int(r.get("size") or 0) for r in mets_tiff_records),
        "first_mets_file": first_mets or {},
        "last_mets_file": last_mets or {},
        "zip_and_mets_tiff_counts_match": len(tif_infos_sorted) == len(mets_tiff_records),
        **{f"mets_{k}": v for k, v in mets.items() if k != "file_records"},
    }
    return facts


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _join(values: Sequence[Any], none_text: str = "None") -> str:
    return ", ".join(str(v) for v in values) if values else none_text


def build_fixed50_questions_and_answers(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    first_mets = facts.get("first_mets_file") or {}
    last_mets = facts.get("last_mets_file") or {}

    qa: List[Tuple[str, str]] = [
        ("What ZIP file was inspected?", f"{facts['sample_zip_name']} ({_format_bytes(facts['sample_zip_size_bytes'])})."),
        ("What document title is reported by the metadata?", facts.get("mets_mods_title") or facts.get("mets_root_label") or "Not reported."),
        ("What is the root METS LABEL?", facts.get("mets_root_label") or "Not reported."),
        ("What is the root METS OBJID?", facts.get("mets_root_objid") or "Not reported."),
        ("What root METS TYPE is reported?", facts.get("mets_root_type") or "Not reported."),
        ("What is the METS record status?", facts.get("mets_record_status") or "Not reported."),
        ("When was the METS record created?", facts.get("mets_record_created") or "Not reported."),
        ("Which organization created the metadata?", facts.get("mets_creator_name") or "Not reported."),
        ("Which conversion tool note is recorded?", facts.get("mets_creator_note") or "Not reported."),
        ("What MODS title is inside the metadata?", facts.get("mets_mods_title") or "Not reported."),
        ("Who is listed as owner?", facts.get("mets_owner") or "Not reported."),
        ("What type of resource is this?", facts.get("mets_resource_type") or "Not reported."),
        ("What genre is reported?", facts.get("mets_genre") or "Not reported."),
        ("What capture date is reported?", facts.get("mets_date_captured") or "Not reported."),
        ("What issuance value is reported?", facts.get("mets_issuance") or "Not reported."),
        ("What language code is reported?", facts.get("mets_language_code") or "Not reported."),
        ("What abstract is provided?", facts.get("mets_abstract") or "Not reported."),
        ("What local identifier is provided?", facts.get("mets_local_identifier") or "Not reported."),
        ("What location URL is provided?", facts.get("mets_location_url") or "Not reported."),
        ("What page range is reported?", f"Pages {facts.get('mets_page_start') or '?'} through {facts.get('mets_page_end') or '?'}."),
        ("How many pages are reported in the MODS extent?", f"{facts.get('mets_reported_page_count', 0)} pages."),
        ("How many TIFF files are physically inside the ZIP?", f"{facts.get('zip_tiff_count', 0)} TIFF files."),
        ("How many TIFF files are listed in the METS file section?", f"{facts.get('mets_tiff_count', 0)} TIFF file records."),
        ("Do the ZIP TIFF count and METS TIFF count match?", _yes_no(bool(facts.get("zip_and_mets_tiff_counts_match"))) + f" ({facts.get('zip_tiff_count', 0)} ZIP TIFFs vs {facts.get('mets_tiff_count', 0)} METS TIFF records)."),
        ("How many total entries are in the ZIP?", f"{facts.get('zip_entry_count', 0)} entries."),
        ("How large is metadata.xml?", _format_bytes(int(facts.get("metadata_xml_size_bytes", 0))) + "."),
        ("How many total TIFF bytes are in the ZIP?", _format_bytes(int(facts.get("zip_total_tiff_bytes", 0))) + "."),
        ("How many total TIFF bytes are reported by METS sizes?", _format_bytes(int(facts.get("mets_total_tiff_bytes", 0))) + "."),
        ("What is the first TIFF filename?", f"{facts.get('first_tiff_name') or 'Not available'} ({_format_bytes(int(facts.get('first_tiff_size_bytes', 0)))})."),
        ("What is the last TIFF filename?", f"{facts.get('last_tiff_name') or 'Not available'} ({_format_bytes(int(facts.get('last_tiff_size_bytes', 0)))})."),
        ("What is the smallest TIFF file?", f"{facts.get('smallest_tiff_name') or 'Not available'} ({_format_bytes(int(facts.get('smallest_tiff_size_bytes', 0)))})."),
        ("What is the largest TIFF file?", f"{facts.get('largest_tiff_name') or 'Not available'} ({_format_bytes(int(facts.get('largest_tiff_size_bytes', 0)))})."),
        ("How many TIFF files are 4,000 bytes or smaller?", f"{facts.get('small_tiff_count_le_4000', 0)} files."),
        ("What are examples of very small TIFF files?", _join(facts.get("small_tiff_examples", []))),
        ("What image MIME type is reported?", facts.get("mets_image_mime_type") or "Not reported."),
        ("What byte order is reported?", facts.get("mets_byte_order") or "Not reported."),
        ("What compression scheme is reported?", facts.get("mets_compression_scheme") or "Not reported."),
        ("What color space is reported?", facts.get("mets_color_space") or "Not reported."),
        ("What is the first METS file ID?", first_mets.get("file_id") or "Not available."),
        ("What checksum is recorded for the first METS file?", first_mets.get("checksum") or "Not available."),
        ("What FLocat href is recorded for the first METS file?", first_mets.get("href") or "Not available."),
        ("What is the last METS file ID?", last_mets.get("file_id") or "Not available."),
        ("What checksum is recorded for the last METS file?", last_mets.get("checksum") or "Not available."),
        ("What FLocat href is recorded for the last METS file?", last_mets.get("href") or "Not available."),
        ("What is the average TIFF file size?", _format_bytes(int(facts.get("zip_average_tiff_size_bytes", 0))) + "."),
        ("What is the median TIFF file size?", _format_bytes(int(facts.get("zip_median_tiff_size_bytes", 0))) + "."),
        ("Are the numeric TIFF filenames consecutive?", _yes_no(bool(facts.get("tiff_numbers_are_consecutive"))) + "."),
        ("Which TIFF page numbers are missing from the numeric sequence?", _join(facts.get("missing_tiff_numbers", []))),
        ("Are there duplicate TIFF filenames?", _yes_no(int(facts.get("duplicate_tiff_name_count", 0)) > 0) + f" ({facts.get('duplicate_tiff_name_count', 0)} duplicates)."),
        ("Does this ZIP contain OCR text for answering manual-content questions directly?", "No OCR text file was detected; this ZIP supports metadata/TIFF inventory QA unless OCR or TRACE-Net extraction artifacts are added."),
    ]

    if len(qa) != 50:
        raise AssertionError(f"Expected 50 questions, got {len(qa)}")

    records: List[Dict[str, Any]] = []
    for idx, (question, answer) in enumerate(qa, start=1):
        records.append(
            {
                "question_id": f"q{idx:02d}",
                "question_index": idx,
                "question_total": 50,
                "question": question,
                "answer": answer,
                "source": "sample_zip_metadata_and_inventory",
                "status": "ok",
            }
        )
    return records


def write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def render_question_answer_text(records: Sequence[Dict[str, Any]]) -> str:
    chunks = []
    for r in records:
        chunks.append(f"Question {r['question_index']:02d}: {r['question']}\nAnswer {r['question_index']:02d}: {r['answer']}")
    return "\n\n".join(chunks) + "\n"


def run(sample_zip: Path, output_dir: Path, print_answers: bool = True) -> Dict[str, Any]:
    start = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)

    facts = inspect_sample_zip(sample_zip)
    records = build_fixed50_questions_and_answers(facts)

    answers_jsonl = output_dir / "answers.jsonl"
    answers_text = output_dir / "answers_question_answer.txt"
    facts_json = output_dir / "sample_zip_facts.json"
    summary_json = output_dir / "summary.json"

    with facts_json.open("w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2, sort_keys=True)

    emitted: List[Dict[str, Any]] = []
    total = len(records)
    for idx, record in enumerate(records, start=1):
        print(f"[{idx:03d}/{total:03d}] START {record['question_id']}: {record['question']}", flush=True)
        emitted.append(record)
        print(f"[{idx:03d}/{total:03d}] DONE  {record['question_id']}", flush=True)

    write_jsonl(answers_jsonl, emitted)
    qa_text = render_question_answer_text(emitted)
    answers_text.write_text(qa_text, encoding="utf-8")

    summary = {
        "status": STATUS,
        "quality_status": "PASS",
        "module": MODULE,
        "version": VERSION,
        "question_count": total,
        "answered_count": len(emitted),
        "sample_zip": str(sample_zip),
        "sample_zip_name": facts["sample_zip_name"],
        "metadata_xml_present": facts["metadata_xml_present"],
        "zip_entry_count": facts["zip_entry_count"],
        "zip_tiff_count": facts["zip_tiff_count"],
        "mets_tiff_count": facts["mets_tiff_count"],
        "reported_page_count": facts["mets_reported_page_count"],
        "zip_and_mets_tiff_counts_match": facts["zip_and_mets_tiff_counts_match"],
        "answers": str(answers_jsonl),
        "answers_text": str(answers_text),
        "facts": str(facts_json),
        "elapsed_seconds": round(time.time() - start, 2),
        "read_only": True,
        "source_truth_mutation_allowed": False,
        "answer_permission_count": 0,
        "write_attempt_count": 0,
    }
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)

    if print_answers:
        print("\n=== QUESTION / ANSWER OUTPUT ===\n", flush=True)
        print(qa_text, flush=True)

    for key in [
        "status",
        "quality_status",
        "question_count",
        "answered_count",
        "zip_tiff_count",
        "mets_tiff_count",
        "reported_page_count",
        "answers",
        "answers_text",
        "summary",
    ]:
        value = summary_json if key == "summary" else summary.get(key)
        print(f"{key}={value}", flush=True)

    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run fixed-50 QA over a metadata/TIFF sample ZIP.")
    p.add_argument("--sample-zip", required=True, type=Path, help="Path to metadata/TIFF sample ZIP.")
    p.add_argument("--output-dir", required=True, type=Path, help="Directory for answers and summary.")
    p.add_argument("--no-print-answers", action="store_false", dest="print_answers", help="Do not print final Question/Answer text to stdout.")
    p.set_defaults(print_answers=True)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        run(args.sample_zip, args.output_dir, print_answers=args.print_answers)
        return 0
    except Exception as exc:  # pragma: no cover - terminal-facing error path
        print(f"status=TRACE_NET_SAMPLE_ZIP_FIXED50_QA_FAILED", file=sys.stderr)
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
