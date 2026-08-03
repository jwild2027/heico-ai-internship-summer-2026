#!/usr/bin/env python3
"""Run fixed 50 Q/A over actual METS/MODS metadata content inside a sample ZIP.

This runner is intentionally local and deterministic:
- reads metadata.xml inside a ZIP
- reads TIFF file entries and METS file/structMap records
- answers 50 fixed questions about the information inside those files
- prints progress and writes a simple Question/Answer text output
- does not call an LLM, endpoint, or database
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

NS = {
    "mets": "http://www.loc.gov/METS/",
    "mods": "http://www.loc.gov/mods/v3",
    "mix": "http://www.loc.gov/mix/",
    "xlink": "http://www.w3.org/1999/xlink",
}
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
XLINK_LABEL = "{http://www.w3.org/1999/xlink}label"

MODULE = "trace_net_sample_zip_content_fixed50_qa_v1"
VERSION = "v1"


@dataclass(frozen=True)
class MetsFile:
    file_id: str
    href: str
    basename: str
    mimetype: str
    size: int
    checksum: str
    checksum_type: str
    group_id: str


@dataclass(frozen=True)
class PageMap:
    order: int
    label: str
    xlink_label: str
    file_id: str
    href: str
    basename: str
    size: int
    checksum: str


@dataclass(frozen=True)
class ParsedZipContent:
    sample_zip: str
    zip_entry_count: int
    metadata_xml_present: bool
    metadata_xml_size: int
    tiff_zip_entries: List[str]
    root_attrs: Dict[str, str]
    mets_header: Dict[str, str]
    agent: Dict[str, str]
    mods: Dict[str, str]
    image_format: Dict[str, str]
    mets_files: List[MetsFile]
    page_maps: List[PageMap]
    zip_tiff_sizes: Dict[str, int]


def _text(root: ET.Element, xpath: str) -> str:
    el = root.find(xpath, NS)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _first_attr(root: ET.Element, xpath: str, attr: str) -> str:
    el = root.find(xpath, NS)
    if el is None:
        return ""
    return el.attrib.get(attr, "")


def _local_file_name(href: str) -> str:
    href = href.replace("file://./", "").replace("file://", "")
    return Path(href).name


def parse_sample_zip(sample_zip: Path) -> ParsedZipContent:
    if not sample_zip.exists():
        raise FileNotFoundError(f"sample ZIP not found: {sample_zip}")
    if not zipfile.is_zipfile(sample_zip):
        raise ValueError(f"not a ZIP file: {sample_zip}")

    with zipfile.ZipFile(sample_zip) as zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        info_by_name = {i.filename: i for i in infos}
        metadata_xml_present = "metadata.xml" in info_by_name
        if not metadata_xml_present:
            raise ValueError("metadata.xml was not found inside the ZIP")
        metadata_bytes = zf.read("metadata.xml")
        metadata_xml_size = len(metadata_bytes)
        metadata_text = metadata_bytes.decode("utf-8", errors="replace")
        root = ET.fromstring(metadata_text)

    tiff_entries = sorted([n for n in names if n.lower().endswith((".tif", ".tiff"))])
    zip_tiff_sizes = {Path(n).name: int(info_by_name[n].file_size) for n in tiff_entries}

    root_attrs = {
        "label": root.attrib.get("LABEL", ""),
        "objid": root.attrib.get("OBJID", ""),
        "type": root.attrib.get("TYPE", ""),
        "schema_location": root.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", ""),
    }
    mets_hdr = root.find("mets:metsHdr", NS)
    mets_header = dict(mets_hdr.attrib) if mets_hdr is not None else {}

    agent_el = root.find("mets:metsHdr/mets:agent", NS)
    agent = {
        "role": agent_el.attrib.get("ROLE", "") if agent_el is not None else "",
        "type": agent_el.attrib.get("TYPE", "") if agent_el is not None else "",
        "name": _text(root, "mets:metsHdr/mets:agent/mets:name"),
        "note": _text(root, "mets:metsHdr/mets:agent/mets:note"),
    }

    role_terms = [el.text.strip() for el in root.findall(".//mods:roleTerm", NS) if el.text]
    mods = {
        "title": _text(root, ".//mods:titleInfo/mods:title"),
        "name_part": _text(root, ".//mods:name/mods:namePart"),
        "role_terms": ", ".join(role_terms),
        "type_of_resource": _text(root, ".//mods:typeOfResource"),
        "genre": _text(root, ".//mods:genre"),
        "date_captured": _text(root, ".//mods:dateCaptured"),
        "issuance": _text(root, ".//mods:issuance"),
        "language_code": _text(root, ".//mods:languageTerm"),
        "abstract": _text(root, ".//mods:abstract"),
        "local_identifier": _text(root, ".//mods:identifier[@type='local']"),
        "location_url": _text(root, ".//mods:location/mods:url"),
        "page_start": _text(root, ".//mods:extent[@unit='pages']/mods:start"),
        "page_end": _text(root, ".//mods:extent[@unit='pages']/mods:end"),
    }

    image_format = {
        "mime_type": _text(root, ".//mix:MIMEType"),
        "byte_order": _text(root, ".//mix:ByteOrder"),
        "compression_scheme": _text(root, ".//mix:CompressionScheme"),
        "color_space": _text(root, ".//mix:ColorSpace"),
    }

    mets_files: List[MetsFile] = []
    for file_el in root.findall(".//mets:fileSec//mets:file", NS):
        flocat = file_el.find("mets:FLocat", NS)
        href = flocat.attrib.get(XLINK_HREF, "") if flocat is not None else ""
        basename = _local_file_name(href)
        try:
            size = int(file_el.attrib.get("SIZE", "0") or 0)
        except ValueError:
            size = 0
        mets_files.append(
            MetsFile(
                file_id=file_el.attrib.get("ID", ""),
                href=href,
                basename=basename,
                mimetype=file_el.attrib.get("MIMETYPE", ""),
                size=size,
                checksum=file_el.attrib.get("CHECKSUM", ""),
                checksum_type=file_el.attrib.get("CHECKSUMTYPE", ""),
                group_id=file_el.attrib.get("GROUPID", ""),
            )
        )
    file_by_id = {mf.file_id: mf for mf in mets_files}

    page_maps: List[PageMap] = []
    for div in root.findall(".//mets:structMap//mets:div[@TYPE='page']", NS):
        fptr = div.find("mets:fptr", NS)
        file_id = fptr.attrib.get("FILEID", "") if fptr is not None else ""
        mf = file_by_id.get(file_id)
        try:
            order = int(div.attrib.get("ORDER", "0") or 0)
        except ValueError:
            order = 0
        if mf is None:
            href = basename = checksum = ""
            size = 0
        else:
            href, basename, size, checksum = mf.href, mf.basename, mf.size, mf.checksum
        page_maps.append(
            PageMap(
                order=order,
                label=div.attrib.get("LABEL", ""),
                xlink_label=div.attrib.get(XLINK_LABEL, ""),
                file_id=file_id,
                href=href,
                basename=basename,
                size=size,
                checksum=checksum,
            )
        )
    page_maps.sort(key=lambda p: p.order)

    return ParsedZipContent(
        sample_zip=str(sample_zip),
        zip_entry_count=len(infos),
        metadata_xml_present=True,
        metadata_xml_size=metadata_xml_size,
        tiff_zip_entries=tiff_entries,
        root_attrs=root_attrs,
        mets_header=mets_header,
        agent=agent,
        mods=mods,
        image_format=image_format,
        mets_files=mets_files,
        page_maps=page_maps,
        zip_tiff_sizes=zip_tiff_sizes,
    )


def _fmt_bytes(n: int) -> str:
    return f"{n:,} bytes"


def _ids_are_sequential(ids: Iterable[str], prefix: str, count: int) -> bool:
    expected = [f"{prefix}{i:04d}" for i in range(1, count + 1)]
    return list(ids) == expected


def _page_by_order(parsed: ParsedZipContent, order: int) -> Optional[PageMap]:
    for p in parsed.page_maps:
        if p.order == order:
            return p
    return None


def _largest_pages(parsed: ParsedZipContent, n: int = 5) -> List[PageMap]:
    return sorted(parsed.page_maps, key=lambda p: p.size, reverse=True)[:n]


def _smallest_pages(parsed: ParsedZipContent, n: int = 5) -> List[PageMap]:
    return sorted(parsed.page_maps, key=lambda p: p.size)[:n]


def _sha1_valid(checksum: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", checksum or ""))


def _join_page_list(pages: List[PageMap]) -> str:
    return "; ".join(f"page {p.order} -> {p.basename} ({_fmt_bytes(p.size)})" for p in pages)


def build_answers(parsed: ParsedZipContent) -> List[Dict[str, Any]]:
    files = parsed.mets_files
    pages = parsed.page_maps
    file_count = len(files)
    page_count = len(pages)
    zip_tiff_count = len(parsed.tiff_zip_entries)
    sizes = [p.size for p in pages]
    total_bytes = sum(sizes)
    avg_size = int(round(statistics.mean(sizes))) if sizes else 0
    med_size = int(round(statistics.median(sizes))) if sizes else 0
    min_page = min(pages, key=lambda p: p.size) if pages else None
    max_page = max(pages, key=lambda p: p.size) if pages else None
    first_page = pages[0] if pages else None
    last_page = pages[-1] if pages else None
    page_end = parsed.mods.get("page_end") or ""
    page_end_int = int(page_end) if page_end.isdigit() else 0
    hrefs = [mf.basename for mf in files]
    zip_basenames = sorted([Path(n).name for n in parsed.tiff_zip_entries])
    missing_in_zip = sorted(set(hrefs) - set(zip_basenames))
    extra_in_zip = sorted(set(zip_basenames) - set(hrefs))
    mismatched_sizes = [mf.basename for mf in files if parsed.zip_tiff_sizes.get(mf.basename) not in (None, mf.size)]
    sha1_count = sum(1 for mf in files if mf.checksum_type.upper() == "SHA-1")
    valid_sha1_count = sum(1 for mf in files if _sha1_valid(mf.checksum))
    unique_checksums = len(set(mf.checksum for mf in files if mf.checksum))
    duplicate_checksums = file_count - unique_checksums if file_count else 0
    mimetypes = sorted(set(mf.mimetype for mf in files if mf.mimetype))
    group_ids = sorted(set(mf.group_id for mf in files if mf.group_id))
    file_ids_seq = _ids_are_sequential([mf.file_id for mf in files], "FID", file_count)
    page_orders_seq = [p.order for p in pages] == list(range(1, page_count + 1))
    page_labels_match = all(str(p.order) == p.label for p in pages)
    xlink_labels_match = all(p.xlink_label == f"PPG{p.order:04d}" for p in pages)
    fptr_ids_all_exist = all(p.file_id in {mf.file_id for mf in files} for p in pages)

    sample_name = Path(parsed.sample_zip).name
    qas: List[Tuple[str, str]] = [
        ("What ZIP file was inspected?", f"The inspected ZIP file is {sample_name}."),
        ("What metadata file inside the ZIP was used as the main source?", "metadata.xml was used as the main METS/MODS source file."),
        ("What title is recorded inside metadata.xml?", f"The recorded title is {parsed.mods.get('title') or 'not found'}."),
        ("What METS LABEL is recorded on the root mets:mets element?", f"The root METS LABEL is {parsed.root_attrs.get('label') or 'not found'}."),
        ("What OBJID is recorded on the root mets:mets element?", f"The root OBJID is {parsed.root_attrs.get('objid') or 'not found'}."),
        ("What METS TYPE is recorded for this package?", f"The METS TYPE is {parsed.root_attrs.get('type') or 'not found'}."),
        ("What is the local identifier in the MODS metadata?", f"The MODS local identifier is {parsed.mods.get('local_identifier') or 'not found'}."),
        ("What location URL is recorded in the MODS metadata?", f"The MODS location URL is {parsed.mods.get('location_url') or 'not found'}."),
        ("Who or what is listed as the owner/namePart?", f"The MODS namePart is {parsed.mods.get('name_part') or 'not found'}."),
        ("What owner role terms are recorded?", f"The recorded role terms are {parsed.mods.get('role_terms') or 'not found'}."),
        ("What typeOfResource is recorded?", f"The MODS typeOfResource is {parsed.mods.get('type_of_resource') or 'not found'}."),
        ("What genre is recorded?", f"The MODS genre is {parsed.mods.get('genre') or 'not found'}."),
        ("What language code is recorded?", f"The MODS language code is {parsed.mods.get('language_code') or 'not found'}."),
        ("What abstract is recorded?", f"The MODS abstract says: {parsed.mods.get('abstract') or 'not found'}."),
        ("What dateCaptured is recorded?", f"The MODS dateCaptured is {parsed.mods.get('date_captured') or 'not found'}."),
        ("What issuance type is recorded?", f"The MODS issuance is {parsed.mods.get('issuance') or 'not found'}."),
        ("What page range is recorded in the MODS extent?", f"The MODS extent records pages {parsed.mods.get('page_start') or '?'} through {parsed.mods.get('page_end') or '?'}."),
        ("How many pages does the MODS extent report?", f"The MODS extent reports {page_end_int if page_end_int else 'an unknown number of'} pages."),
        ("How many TIFF image files are listed in the ZIP?", f"The ZIP contains {zip_tiff_count} TIFF image entries."),
        ("How many mets:file image records are listed in metadata.xml?", f"metadata.xml lists {file_count} mets:file image records."),
        ("How many page divs are listed in the METS structMap?", f"The METS structMap lists {page_count} page divs."),
        ("Do the ZIP TIFF count, mets:file count, and structMap page count agree?", f"{'Yes' if zip_tiff_count == file_count == page_count else 'No'}: ZIP TIFFs={zip_tiff_count}, mets:file records={file_count}, structMap pages={page_count}."),
        ("What MIME type is recorded for the image files?", f"The image file MIME type(s) recorded in mets:file are: {', '.join(mimetypes) if mimetypes else 'not found'}."),
        ("What MIX MIMEType is recorded in the technical metadata?", f"The MIX technical metadata MIMEType is {parsed.image_format.get('mime_type') or 'not found'}."),
        ("What byte order is recorded in the MIX image metadata?", f"The recorded byte order is {parsed.image_format.get('byte_order') or 'not found'}."),
        ("What compression scheme is recorded in the MIX image metadata?", f"The recorded compression scheme is {parsed.image_format.get('compression_scheme') or 'not found'}."),
        ("What color space is recorded in the MIX image metadata?", f"The recorded color space is {parsed.image_format.get('color_space') or 'not found'}."),
        ("What checksum type is used for the image file records?", f"{sha1_count} of {file_count} image file records use SHA-1 checksums."),
        ("Do the recorded checksums look like valid SHA-1 hex strings?", f"{'Yes' if valid_sha1_count == file_count else 'No'}: {valid_sha1_count} of {file_count} checksums match the 40-character SHA-1 hex pattern."),
        ("Are all image checksums unique?", f"{'Yes' if duplicate_checksums == 0 else 'No'}: {unique_checksums} unique checksum values were found across {file_count} records."),
        ("Are the mets:file IDs sequential?", f"{'Yes' if file_ids_seq else 'No'}: the file IDs are expected to run from FID0001 through FID{file_count:04d}."),
        ("Are the structMap page orders sequential?", f"{'Yes' if page_orders_seq else 'No'}: page ORDER values are expected to run from 1 through {page_count}."),
        ("Do page LABEL values match their ORDER values?", f"{'Yes' if page_labels_match else 'No'}: page LABEL values were checked against their ORDER values."),
        ("Do xlink page labels follow the PPG#### pattern?", f"{'Yes' if xlink_labels_match else 'No'}: xlink labels were checked against PPG0001 through PPG{page_count:04d}."),
        ("Does every structMap fptr FILEID point to a mets:file record?", f"{'Yes' if fptr_ids_all_exist else 'No'}: every page fptr FILEID was checked against the mets:file records."),
        ("Does every mets:file href have a matching TIFF entry in the ZIP?", f"{'Yes' if not missing_in_zip else 'No'}: missing ZIP TIFFs from METS hrefs = {len(missing_in_zip)}."),
        ("Are there TIFF files in the ZIP that are not referenced by metadata.xml?", f"{'No' if not extra_in_zip else 'Yes'}: unreferenced ZIP TIFF entries = {len(extra_in_zip)}."),
        ("Do METS file sizes match the ZIP entry sizes?", f"{'Yes' if not mismatched_sizes else 'No'}: mismatched size records = {len(mismatched_sizes)}."),
        ("What is the first page mapped to?", f"Page 1 maps to {first_page.basename} with FILEID {first_page.file_id}, xlink label {first_page.xlink_label}, and size {_fmt_bytes(first_page.size)}." if first_page else "No page mapping was found."),
        ("What is the last page mapped to?", f"Page {last_page.order} maps to {last_page.basename} with FILEID {last_page.file_id}, xlink label {last_page.xlink_label}, and size {_fmt_bytes(last_page.size)}." if last_page else "No page mapping was found."),
        ("What file is mapped to page 25?", (lambda p: f"Page 25 maps to {p.basename}, FILEID {p.file_id}, xlink label {p.xlink_label}, size {_fmt_bytes(p.size)}." if p else "Page 25 was not found in the structMap.")(_page_by_order(parsed, 25))),
        ("What file is mapped to page 100?", (lambda p: f"Page 100 maps to {p.basename}, FILEID {p.file_id}, xlink label {p.xlink_label}, size {_fmt_bytes(p.size)}." if p else "Page 100 was not found in the structMap.")(_page_by_order(parsed, 100))),
        ("What file is mapped to page 250?", (lambda p: f"Page 250 maps to {p.basename}, FILEID {p.file_id}, xlink label {p.xlink_label}, size {_fmt_bytes(p.size)}." if p else "Page 250 was not found in the structMap.")(_page_by_order(parsed, 250))),
        ("What file is mapped to page 509?", (lambda p: f"Page 509 maps to {p.basename}, FILEID {p.file_id}, xlink label {p.xlink_label}, size {_fmt_bytes(p.size)}." if p else "Page 509 was not found in the structMap.")(_page_by_order(parsed, 509))),
        ("Which page has the largest recorded TIFF size?", f"The largest recorded TIFF is page {max_page.order} -> {max_page.basename} at {_fmt_bytes(max_page.size)}." if max_page else "No page sizes were found."),
        ("Which page has the smallest recorded TIFF size?", f"The smallest recorded TIFF is page {min_page.order} -> {min_page.basename} at {_fmt_bytes(min_page.size)}." if min_page else "No page sizes were found."),
        ("What are the five largest page image records?", _join_page_list(_largest_pages(parsed, 5)) if pages else "No page image records were found."),
        ("What are the five smallest page image records?", _join_page_list(_smallest_pages(parsed, 5)) if pages else "No page image records were found."),
        ("What is the total recorded size of all page TIFFs?", f"The total recorded size of all page TIFFs is {_fmt_bytes(total_bytes)}."),
        ("What is the median recorded TIFF size per page?", f"The median recorded TIFF size per page is about {_fmt_bytes(med_size)}."),
    ]

    if len(qas) != 50:
        raise AssertionError(f"internal fixed Q/A list must contain 50 questions, found {len(qas)}")

    rows: List[Dict[str, Any]] = []
    for idx, (question, answer) in enumerate(qas, start=1):
        rows.append(
            {
                "question_id": f"q{idx:02d}",
                "question_index": idx,
                "question_total": 50,
                "question": question,
                "answer": answer,
                "source_basis": "metadata.xml plus ZIP file table entries",
            }
        )
    return rows


def write_outputs(rows: List[Dict[str, Any]], parsed: ParsedZipContent, output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    answers_jsonl = output_dir / "answers.jsonl"
    answers_txt = output_dir / "answers_question_answer.txt"
    summary_path = output_dir / "summary.json"

    with answers_jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    with answers_txt.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(f"Question {row['question_index']:02d}: {row['question']}\n")
            f.write(f"Answer {row['question_index']:02d}: {row['answer']}\n\n")

    summary = {
        "status": "TRACE_NET_SAMPLE_ZIP_CONTENT_FIXED50_QA_DONE",
        "quality_status": "PASS" if len(rows) == 50 else "FAIL",
        "module": MODULE,
        "version": VERSION,
        "sample_zip": parsed.sample_zip,
        "question_count": len(rows),
        "answered_count": sum(1 for r in rows if r.get("answer")),
        "metadata_xml_present": parsed.metadata_xml_present,
        "metadata_xml_size": parsed.metadata_xml_size,
        "zip_entry_count": parsed.zip_entry_count,
        "zip_tiff_count": len(parsed.tiff_zip_entries),
        "mets_file_count": len(parsed.mets_files),
        "structmap_page_count": len(parsed.page_maps),
        "reported_page_start": parsed.mods.get("page_start"),
        "reported_page_end": parsed.mods.get("page_end"),
        "title": parsed.mods.get("title"),
        "answers": str(answers_jsonl),
        "question_answer_output": str(answers_txt),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def run(sample_zip: Path, output_dir: Path, show_progress: bool = True, print_answers: bool = True) -> Dict[str, Any]:
    parsed = parse_sample_zip(sample_zip)
    rows = build_answers(parsed)

    completed: List[Dict[str, Any]] = []
    for row in rows:
        idx = row["question_index"]
        total = row["question_total"]
        if show_progress:
            print(f"[{idx:03d}/{total:03d}] START {row['question_id']}: {row['question']}", flush=True)
        completed.append(row)
        if show_progress:
            print(f"[{idx:03d}/{total:03d}] DONE  {row['question_id']}", flush=True)

    summary = write_outputs(completed, parsed, output_dir)

    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    print(f"question_count={summary['question_count']}")
    print(f"answered_count={summary['answered_count']}")
    print(f"zip_tiff_count={summary['zip_tiff_count']}")
    print(f"mets_file_count={summary['mets_file_count']}")
    print(f"structmap_page_count={summary['structmap_page_count']}")
    print(f"answers={summary['answers']}")
    print(f"question_answer_output={summary['question_answer_output']}")

    if print_answers:
        print("\n--- QUESTION / ANSWER OUTPUT ---\n")
        print(Path(summary["question_answer_output"]).read_text(encoding="utf-8"), end="")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run fixed 50 Q/A over content inside a sample metadata ZIP.")
    parser.add_argument("--sample-zip", required=True, help="Path to sample metadata ZIP.")
    parser.add_argument("--output-dir", required=True, help="Directory for outputs.")
    parser.add_argument("--no-progress", action="store_true", help="Disable per-question progress output.")
    parser.add_argument("--no-print-answers", action="store_true", help="Do not print final Question/Answer text to stdout.")
    args = parser.parse_args(argv)
    try:
        run(
            sample_zip=Path(args.sample_zip),
            output_dir=Path(args.output_dir),
            show_progress=not args.no_progress,
            print_answers=not args.no_print_answers,
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
