#!/usr/bin/env python3
"""TRACE-Net NHA phases N0-N3: inventory, assembly anchors, IPL rows, relationships.

This module is intentionally read-only and deterministic. It does not write to
Postgres, Qdrant, OpenSearch, or any production graph. It builds JSON artifacts
that can be inspected and quality-gated before a later graph-load phase.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_nha_phase0_3_v1"
STATUS = "TRACE_NET_NHA_PHASE0_3_V1"
SCHEMA_VERSION = "trace_net_nha_phase0_3_v1"

METS_NS = "http://www.loc.gov/METS/"
MODS_NS = "http://www.loc.gov/mods/v3"
XLINK_NS = "http://www.w3.org/1999/xlink"
NS = {"mets": METS_NS, "mods": MODS_NS, "xlink": XLINK_NS}

FULL_PART_RE = re.compile(r"\b\d{2,4}-\d{4,6}-\d{3}\b", re.I)
PRINTED_GROUP_RE = re.compile(r"\b(?P<base>\d{2,4}-\d{4,6}-\d{3})(?P<suffixes>(?:/\d{3})+)\b", re.I)
GENERIC_PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?|\d{4,6}-\d{1,4}|[A-Z]{2,}\d{3,}[A-Z0-9./-]*)\b",
    re.I,
)
ANCHOR_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ,/&.'-]{3,160}?)\s*"
    r"\((?P<printed>\d{2,4}-\d{4,6}-\d{3}(?:/\d{3})*)\)\s*$",
    re.I,
)
FIGURE_RE = re.compile(r"\bFigure\s+(?P<figure>[A-Z0-9-]+)\b", re.I)
SHEET_RE = re.compile(r"\bSheet\s+(?P<sheet>\d+)\b", re.I)
PRINTED_PAGE_RE = re.compile(r"\bPage\s+(?P<page>\d+)\b", re.I)
EFFECTIVITY_RE = re.compile(r"\bEFFECTIVITY\s*:\s*(?P<value>.+)$", re.I)
ROW_RE = re.compile(
    r"^\s*(?:(?P<figure_column>\d+)\s+)?(?P<item>-?\d+|-)\s*\|\s*"
    r"(?P<part>[A-Z0-9][A-Z0-9./-]{3,})\s+(?P<rest>.+?)\s*$",
    re.I,
)
REVISION_RE = re.compile(r"\bREV\.?\s*(?P<revision>\d+)\b", re.I)
ATA_RE = re.compile(r"\bATA\s+(?P<ata>\d{2}-\d{2}-\d{2})\b", re.I)
SEPARATOR_RE = re.compile(r"[-_=]{2,}\s*\*\s*[-_=]{2,}")

ASSEMBLY_WORDS = (
    "assembly", "assy", "structure", "seat", "backrest", "armrest",
    "support", "frame", "unit", "module",
)


def _compact(value: Any, limit: int = 20000) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _stable_id(prefix: str, *values: Any) -> str:
    blob = "|".join(_compact(value, 5000) for value in values)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in (
            "records", "items", "pages", "page_records", "ocr_records",
            "page_context_records", "page_intelligence_cards", "cards",
        ):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _page_id_from_row(row: Mapping[str, Any]) -> str:
    for key in ("page_id", "source_page_id", "document_page_id", "page"):
        value = row.get(key)
        if value:
            return str(value).strip()
    nested = row.get("retrieval_document")
    if isinstance(nested, Mapping):
        return _page_id_from_row(nested)
    return ""


def _ocr_text_from_row(row: Mapping[str, Any], base_path: Path) -> str:
    for key in (
        "ocr_text", "text", "page_text", "ocr_sample_text", "sample_text",
        "content", "normalized_text",
    ):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    rel = str(row.get("ocr_text_path") or "").replace("\\", "/").strip()
    if rel:
        candidates = [Path(rel)]
        if not Path(rel).is_absolute():
            candidates.append(base_path.parent / rel)
            if "local_data/" in rel:
                candidates.append(Path.cwd() / rel)
        for path in candidates:
            try:
                if path.exists():
                    return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    return ""


def load_ocr_index(path: str | Path | None) -> dict[str, str]:
    """Load a flexible JSON/JSONL OCR artifact keyed by canonical page id."""
    if not path:
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    rows: list[dict[str, Any]] = []
    if source.suffix.lower() == ".jsonl":
        with source.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, Mapping):
                    rows.append(dict(value))
    else:
        rows = _json_rows(json.loads(source.read_text(encoding="utf-8")))
    output: dict[str, str] = {}
    for row in rows:
        pid = _page_id_from_row(row)
        text = _ocr_text_from_row(row, source)
        if pid and text.strip() and len(text) > len(output.get(pid, "")):
            output[pid] = text
    return output


@dataclass(frozen=True)
class CorpusSource:
    """Directory or ZIP source containing metadata.xml and TIFF pages."""

    path: Path

    @property
    def is_zip(self) -> bool:
        return self.path.is_file() and zipfile.is_zipfile(self.path)

    def read_bytes(self, member: str) -> bytes:
        if self.is_zip:
            with zipfile.ZipFile(self.path) as archive:
                return archive.read(member)
        return (self.path / member).read_bytes()

    def exists(self, member: str) -> bool:
        if self.is_zip:
            with zipfile.ZipFile(self.path) as archive:
                return member in set(archive.namelist())
        return (self.path / member).exists()

    def member_size(self, member: str) -> int | None:
        if self.is_zip:
            with zipfile.ZipFile(self.path) as archive:
                try:
                    return int(archive.getinfo(member).file_size)
                except KeyError:
                    return None
        path = self.path / member
        return path.stat().st_size if path.exists() else None

    def materialize(self, member: str, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / Path(member).name
        if self.is_zip:
            target.write_bytes(self.read_bytes(member))
        else:
            shutil.copy2(self.path / member, target)
        return target


def parse_page_spec(spec: str, maximum: int | None = None) -> list[int]:
    output: list[int] = []
    seen: set[int] = set()
    for chunk in str(spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            left, right = chunk.split("-", 1)
            start, end = int(left), int(right)
            if end < start:
                start, end = end, start
            values = range(start, end + 1)
        else:
            values = (int(chunk),)
        for value in values:
            if value < 1 or (maximum is not None and value > maximum) or value in seen:
                continue
            seen.add(value)
            output.append(value)
    return output


def expand_printed_part_group(value: str) -> list[str]:
    """Expand ``120-29067-003/021/031`` without losing the printed form."""
    text = str(value or "").strip().upper()
    match = PRINTED_GROUP_RE.fullmatch(text)
    if not match:
        return [text] if FULL_PART_RE.fullmatch(text) else []
    base = match.group("base")
    stem = base.rsplit("-", 1)[0]
    suffixes = [base.rsplit("-", 1)[1], *match.group("suffixes").lstrip("/").split("/")]
    return list(dict.fromkeys(f"{stem}-{suffix}" for suffix in suffixes))


def parse_mets_inventory(
    source: CorpusSource,
    *,
    metadata_member: str = "metadata.xml",
    page_id_prefix: str = "t_p_120_1176_p",
    document_id: str = "120-1176",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = ET.fromstring(source.read_bytes(metadata_member))
    label = str(root.attrib.get("LABEL") or "").strip()
    objid = str(root.attrib.get("OBJID") or "").strip()
    title_node = root.find(".//mods:title", NS)
    title = str(title_node.text or "").strip() if title_node is not None else label
    revision_match = REVISION_RE.search(label + " " + title)
    ata_match = ATA_RE.search(label + " " + title)
    revision = revision_match.group("revision") if revision_match else ""
    ata = ata_match.group("ata") if ata_match else ""

    files: dict[str, dict[str, Any]] = {}
    for node in root.findall(".//mets:fileSec//mets:file", NS):
        file_id = str(node.attrib.get("ID") or "")
        loc = node.find("mets:FLocat", NS)
        href = ""
        if loc is not None:
            href = str(loc.attrib.get(f"{{{XLINK_NS}}}href") or "")
        href = href.replace("file://./", "").replace("file://", "").lstrip("./")
        files[file_id] = {
            "file_id": file_id,
            "tiff_filename": Path(href).name,
            "archive_member": href,
            "declared_size": int(node.attrib.get("SIZE") or 0),
            "checksum": str(node.attrib.get("CHECKSUM") or ""),
            "checksum_type": str(node.attrib.get("CHECKSUMTYPE") or ""),
            "mimetype": str(node.attrib.get("MIMETYPE") or ""),
        }

    inventory: list[dict[str, Any]] = []
    page_nodes = root.findall(".//mets:structMap[@TYPE='physical']//mets:div[@TYPE='page']", NS)
    for fallback_index, page_node in enumerate(page_nodes, 1):
        fptr = page_node.find("mets:fptr", NS)
        file_id = str(fptr.attrib.get("FILEID") or "") if fptr is not None else ""
        file_info = dict(files.get(file_id) or {})
        ordinal = int(page_node.attrib.get("ORDER") or fallback_index)
        filename = str(file_info.get("tiff_filename") or f"{ordinal:08d}.tif")
        member = str(file_info.get("archive_member") or filename)
        actual_size = source.member_size(member)
        inventory.append({
            "schema_version": SCHEMA_VERSION,
            "truth_mode": "real_source",
            "source_truth": True,
            "production_visible": True,
            "document_id": document_id,
            "document_label": label,
            "document_title": title,
            "document_objid": objid,
            "document_revision": revision,
            "ata": ata,
            "page_ordinal": ordinal,
            "page_label": str(page_node.attrib.get("LABEL") or ordinal),
            "canonical_page_id": f"{page_id_prefix}{ordinal:06d}",
            "tiff_filename": filename,
            "archive_member": member,
            "file_id": file_id,
            "mimetype": file_info.get("mimetype") or "image/tiff",
            "declared_size": int(file_info.get("declared_size") or 0),
            "actual_size": actual_size,
            "size_matches_metadata": actual_size == int(file_info.get("declared_size") or 0),
            "checksum": file_info.get("checksum") or "",
            "checksum_type": file_info.get("checksum_type") or "",
            "source_exists": source.exists(member),
        })

    summary = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "document_id": document_id,
        "document_label": label,
        "document_title": title,
        "document_objid": objid,
        "document_revision": revision,
        "ata": ata,
        "page_count": len(inventory),
        "source_exists_count": sum(bool(row["source_exists"]) for row in inventory),
        "size_match_count": sum(bool(row["size_matches_metadata"]) for row in inventory),
    }
    return inventory, summary


def tesseract_ocr(
    source: CorpusSource,
    inventory_row: Mapping[str, Any],
    *,
    tesseract_cmd: str,
    psm: int = 6,
) -> str:
    command = str(tesseract_cmd or "").strip()
    if not command:
        return ""
    with tempfile.TemporaryDirectory(prefix="trace_net_nha_ocr_") as temp:
        temp_path = Path(temp)
        image = source.materialize(str(inventory_row["archive_member"]), temp_path)
        output_base = temp_path / "ocr"
        completed = subprocess.run(
            [command, str(image), str(output_base), "--psm", str(int(psm))],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        text_path = output_base.with_suffix(".txt")
        if completed.returncode != 0 or not text_path.exists():
            return ""
        return text_path.read_text(encoding="utf-8", errors="replace")


def discover_assembly_anchors(page_id: str, text: str) -> list[dict[str, Any]]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in str(text or "").splitlines()]
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, line in enumerate(lines):
        match = ANCHOR_LINE_RE.match(line)
        if not match:
            continue
        name = _compact(match.group("name"), 200)
        if not any(word in name.casefold() for word in ASSEMBLY_WORDS):
            continue
        printed = match.group("printed").upper()
        variants = expand_printed_part_group(printed)
        if not variants:
            continue
        window = lines[max(0, index - 5):min(len(lines), index + 8)]
        window_text = "\n".join(window)
        figure_match = FIGURE_RE.search(window_text)
        sheet_match = SHEET_RE.search(window_text)
        printed_page_match = PRINTED_PAGE_RE.search(window_text)
        effectivity_match = EFFECTIVITY_RE.search(window_text)
        figure = figure_match.group("figure") if figure_match else ""
        sheet = int(sheet_match.group("sheet")) if sheet_match else None
        key = (printed, figure, str(sheet or ""))
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "schema_version": SCHEMA_VERSION,
            "anchor_id": _stable_id("nha_anchor", page_id, printed, figure, sheet),
            "truth_mode": "real_source",
            "source_truth": True,
            "production_visible": True,
            "page_id": page_id,
            "assembly_name": name,
            "assembly_identifier_as_printed": printed,
            "assembly_part_variants": variants,
            "figure": figure,
            "sheet": sheet,
            "printed_manual_page": printed_page_match.group("page") if printed_page_match else "",
            "effectivity_text": _compact(effectivity_match.group("value"), 300) if effectivity_match else "",
            "anchor_method": "figure_or_ipl_title",
            "relationship_status": "assembly_anchor_source_supported",
            "ocr_line_number": index + 1,
            "ocr_line": line,
        })
    return output


def _clean_nomenclature(rest: str) -> tuple[str, str, int]:
    raw = re.sub(r"\|", " ", str(rest or "")).strip()
    indentation = len(re.match(r"^[.\s]*", raw).group(0).replace(" ", "")) if raw else 0
    value = re.sub(r"^\.+\s*", "", raw)
    value = re.sub(r"\.{2,}", " ", value)
    tokens = value.split()
    quantity = ""
    if tokens and (tokens[-1].upper() == "REF" or re.fullmatch(r"\d+(?:\.\d+)?", tokens[-1])):
        quantity = tokens.pop().upper()
    stop = len(tokens)
    for idx, token in enumerate(tokens):
        stripped = token.strip(".,;:()[]")
        if re.fullmatch(r"[A-Z]{2,}\d{3,}", stripped, re.I):
            stop = idx
            break
        if re.fullmatch(r"\d{2,3}/\d{2,3}", stripped):
            stop = idx
            break
        if idx >= 1 and re.fullmatch(r"[A-Z]", stripped):
            stop = idx
            break
    nomenclature = " ".join(tokens[:stop]).strip(" .,-")
    nomenclature = re.sub(r"\s+", " ", nomenclature)
    return nomenclature, quantity, indentation


def reconstruct_ipl_rows(
    page_id: str,
    text: str,
    anchors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    parent_parts = {
        part.upper()
        for anchor in anchors
        for part in anchor.get("assembly_part_variants") or []
    }
    output: list[dict[str, Any]] = []
    attaching_mode = False
    attaching_parent_part = ""
    most_recent_component = ""
    lines = str(text or "").splitlines()
    for index, raw_line in enumerate(lines):
        line = re.sub(r"\s+", " ", raw_line).strip()
        upper = line.upper()
        if "ATTACHING PARTS" in upper:
            attaching_mode = True
            attaching_parent_part = most_recent_component
            continue
        if attaching_mode and SEPARATOR_RE.search(line):
            attaching_mode = False
            attaching_parent_part = ""
            continue
        match = ROW_RE.match(line)
        if not match:
            continue
        item = match.group("item")
        part = match.group("part").upper().strip(".,;")
        if not GENERIC_PART_RE.fullmatch(part):
            continue
        nomenclature, quantity, indentation = _clean_nomenclature(match.group("rest"))
        row_type = "assembly_reference" if part in parent_parts else "component"
        if row_type == "component" and not attaching_mode:
            most_recent_component = part
        output.append({
            "schema_version": SCHEMA_VERSION,
            "row_id": _stable_id("nha_row", page_id, index + 1, item, part, line),
            "truth_mode": "real_source",
            "source_truth": True,
            "production_visible": True,
            "page_id": page_id,
            "figure_column": match.group("figure_column") or "",
            "item_number": item.lstrip("-") if item != "-" else "",
            "item_not_illustrated": item.startswith("-") and item != "-",
            "part_number": part,
            "nomenclature": nomenclature,
            "quantity": quantity,
            "indentation_level": indentation,
            "row_type": row_type,
            "attaching_parts_context": attaching_mode,
            "attaching_parent_candidate": attaching_parent_part if attaching_mode else "",
            "ocr_line_number": index + 1,
            "ocr_line": line,
            "row_reconstruction_status": "exact_line_parse",
        })
    return output


def build_relationships(
    page_id: str,
    anchors: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for anchor in anchors:
        parents = [str(value).upper() for value in anchor.get("assembly_part_variants") or []]
        if not parents:
            continue
        multi_parent = len(parents) > 1
        for row in rows:
            if row.get("row_type") != "component":
                continue
            child = str(row.get("part_number") or "").upper()
            if not child or child in parents:
                continue
            attaching = bool(row.get("attaching_parts_context"))
            if attaching:
                status = "candidate"
                relationship_type = "attaching_part_candidate"
                ambiguity = "attaching_parts_boundary_or_parent_requires_phase_n4"
                parent_candidates = [
                    str(row.get("attaching_parent_candidate") or ""),
                    *parents,
                ]
            elif multi_parent:
                status = "ambiguous"
                relationship_type = "direct_component_candidate"
                ambiguity = "multiple_parent_variants_require_usage_code_or_effectivity_resolution"
                parent_candidates = parents
            else:
                status = "source_supported"
                relationship_type = "direct_component"
                ambiguity = ""
                parent_candidates = parents

            direct_parent = parent_candidates[0] if status == "source_supported" and len(parent_candidates) == 1 else ""
            relationship_id = _stable_id(
                "assembly_membership", page_id, anchor.get("anchor_id"), row.get("row_id"),
                child, direct_parent or ",".join(parent_candidates), relationship_type,
            )
            output.append({
                "schema_version": SCHEMA_VERSION,
                "relationship_id": relationship_id,
                "truth_mode": "real_source",
                "source_truth": True,
                "production_visible": True,
                "relationship_type": relationship_type,
                "relationship_status": status,
                "child_part": child,
                "direct_nha": direct_parent,
                "parent_candidates": list(dict.fromkeys(value for value in parent_candidates if value)),
                "assembly_identifier_as_printed": anchor.get("assembly_identifier_as_printed") or "",
                "assembly_name": anchor.get("assembly_name") or "",
                "quantity": row.get("quantity") or "",
                "item_number": row.get("item_number") or "",
                "figure": anchor.get("figure") or "",
                "sheet": anchor.get("sheet"),
                "anchor_page_id": anchor.get("page_id") or page_id,
                "row_page_id": row.get("page_id") or page_id,
                "anchor_id": anchor.get("anchor_id") or "",
                "row_id": row.get("row_id") or "",
                "parent_resolution_method": "figure_or_ipl_title",
                "child_resolution_method": "exact_ipl_row",
                "same_page_context": (anchor.get("page_id") or page_id) == (row.get("page_id") or page_id),
                "same_figure_context": bool(anchor.get("figure")),
                "attaching_parts_context": attaching,
                "ambiguity_reason": ambiguity,
                "can_prove_direct_nha": status == "source_supported",
                "guidance_only": status != "source_supported",
                "source_truth_mutation_allowed": False,
            })
    dedup: list[dict[str, Any]] = []
    seen = set()
    for row in output:
        key = row["relationship_id"]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(row)
    return dedup


def build_answer_key(relationships: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for relationship in relationships:
        child = str(relationship.get("child_part") or "")
        status = str(relationship.get("relationship_status") or "")
        direct = str(relationship.get("direct_nha") or "")
        parents = [str(value) for value in relationship.get("parent_candidates") or []]
        cases.append({
            "case_id": _stable_id("nha_case", relationship.get("relationship_id")),
            "truth_mode": "real_source",
            "question": f"What is the direct next higher assembly of part {child}?",
            "child_part": child,
            "expected_behavior": "direct_answer" if status == "source_supported" else "candidate_or_clarification",
            "expected_direct_nha": direct,
            "expected_parent_candidates": parents,
            "expected_relationship_order": [child, direct] if direct else [child, *parents],
            "expected_figure": relationship.get("figure") or "",
            "expected_item_number": relationship.get("item_number") or "",
            "expected_quantity": relationship.get("quantity") or "",
            "expected_pages": list(dict.fromkeys([
                str(relationship.get("anchor_page_id") or ""),
                str(relationship.get("row_page_id") or ""),
            ])),
            "relationship_status": status,
            "must_not_claim": (
                [] if direct else [
                    "Any candidate parent is confirmed without usage-code/effectivity or attaching-parts resolution",
                    "A higher ancestor is the direct NHA without an explicit intermediate hop",
                ]
            ),
            "source_relationship_id": relationship.get("relationship_id") or "",
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "truth_mode": "real_source",
        "case_count": len(cases),
        "direct_answer_case_count": sum(row["expected_behavior"] == "direct_answer" for row in cases),
        "candidate_case_count": sum(row["expected_behavior"] != "direct_answer" for row in cases),
        "cases": cases,
    }


def build_graph_bundle(
    inventory: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    *,
    document_id: str,
    revision: str,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    revision_node = f"document_revision:{document_id}:rev{revision or 'unknown'}"
    nodes.append({
        "node_id": revision_node,
        "node_type": "DocumentRevision",
        "properties": {"document_id": document_id, "revision": revision, "truth_mode": "real_source"},
    })
    for page in inventory:
        page_id = str(page.get("canonical_page_id") or "")
        if not page_id:
            continue
        nodes.append({"node_id": f"page:{page_id}", "node_type": "Page", "properties": dict(page)})
        edges.append({"edge_type": "HAS_PAGE", "from": revision_node, "to": f"page:{page_id}", "properties": {}})

    part_ids: set[str] = set()
    for relationship in relationships:
        child = str(relationship.get("child_part") or "")
        parents = [str(value) for value in relationship.get("parent_candidates") or []]
        for part in [child, *parents]:
            if part and part not in part_ids:
                part_ids.add(part)
                nodes.append({
                    "node_id": f"part:{part}",
                    "node_type": "Part",
                    "properties": {"part_number": part, "truth_mode": "real_source"},
                })
        membership = str(relationship.get("relationship_id") or "")
        nodes.append({
            "node_id": membership,
            "node_type": "AssemblyMembership",
            "properties": dict(relationship),
        })
        if child:
            edges.append({"edge_type": "MEMBER_IN", "from": f"part:{child}", "to": membership, "properties": {}})
        for parent in parents:
            edges.append({"edge_type": "PARENT_ASSEMBLY", "from": membership, "to": f"part:{parent}", "properties": {"candidate": relationship.get("relationship_status") != "source_supported"}})
        for pid in dict.fromkeys([
            str(relationship.get("anchor_page_id") or ""),
            str(relationship.get("row_page_id") or ""),
        ]):
            if pid:
                edges.append({"edge_type": "EVIDENCED_BY_PAGE", "from": membership, "to": f"page:{pid}", "properties": {}})
        if relationship.get("relationship_status") == "source_supported":
            parent = str(relationship.get("direct_nha") or "")
            if child and parent:
                properties = {"relationship_id": membership, "source_supported": True}
                edges.append({"edge_type": "DIRECT_COMPONENT_OF", "from": f"part:{child}", "to": f"part:{parent}", "properties": properties})
                edges.append({"edge_type": "HAS_DIRECT_COMPONENT", "from": f"part:{parent}", "to": f"part:{child}", "properties": properties})

    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "truth_mode": "real_source",
        "read_only": True,
        "source_truth_mutation_allowed": False,
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "parts": len(part_ids),
            "assembly_memberships": len(relationships),
            "source_supported_memberships": sum(row.get("relationship_status") == "source_supported" for row in relationships),
        },
    }


def _detect_direct_cycles(relationships: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for row in relationships:
        if row.get("relationship_status") != "source_supported":
            continue
        child = str(row.get("child_part") or "")
        parent = str(row.get("direct_nha") or "")
        if child and parent:
            graph[child].add(parent)
    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            start = stack.index(node) if node in stack else 0
            cycles.append(stack[start:] + [node])
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for nxt in sorted(graph.get(node, set())):
            visit(nxt)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)
    return cycles


def validate_artifacts(
    inventory: Sequence[Mapping[str, Any]],
    anchors: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    *,
    expected_page_count: int = 0,
    min_source_supported: int = 0,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    page_ids = [str(row.get("canonical_page_id") or "") for row in inventory]
    filenames = [str(row.get("tiff_filename") or "") for row in inventory]
    page_set = set(page_ids)
    if expected_page_count and len(inventory) != expected_page_count:
        failures.append(f"inventory_page_count expected={expected_page_count} actual={len(inventory)}")
    if len(page_ids) != len(set(page_ids)):
        failures.append("duplicate_canonical_page_id")
    if len(filenames) != len(set(filenames)):
        failures.append("duplicate_tiff_filename")
    if any(not row.get("source_exists") for row in inventory):
        failures.append("missing_tiff_source")
    if any(row.get("truth_mode") != "real_source" for row in [*inventory, *anchors, *rows, *relationships]):
        failures.append("synthetic_or_unknown_truth_mode_in_phase0_3")
    if any(not row.get("source_truth") for row in [*inventory, *anchors, *rows, *relationships]):
        failures.append("non_source_truth_record_in_phase0_3")

    relationship_ids = [str(row.get("relationship_id") or "") for row in relationships]
    if len(relationship_ids) != len(set(relationship_ids)):
        failures.append("duplicate_relationship_id")
    for relationship in relationships:
        child = str(relationship.get("child_part") or "")
        direct = str(relationship.get("direct_nha") or "")
        if child and direct and child == direct:
            failures.append(f"self_parent_relationship:{relationship.get('relationship_id')}")
        for key in ("anchor_page_id", "row_page_id"):
            pid = str(relationship.get(key) or "")
            if not pid or pid not in page_set:
                failures.append(f"relationship_missing_inventory_page:{relationship.get('relationship_id')}:{key}:{pid}")
        if relationship.get("relationship_status") == "source_supported":
            if not direct:
                failures.append(f"source_supported_missing_direct_nha:{relationship.get('relationship_id')}")
            if len(relationship.get("parent_candidates") or []) != 1:
                failures.append(f"source_supported_parent_count_not_one:{relationship.get('relationship_id')}")
            if relationship.get("guidance_only"):
                failures.append(f"source_supported_marked_guidance:{relationship.get('relationship_id')}")
        else:
            if relationship.get("can_prove_direct_nha"):
                failures.append(f"candidate_can_prove_direct_nha:{relationship.get('relationship_id')}")

    cycles = _detect_direct_cycles(relationships)
    if cycles:
        failures.append(f"direct_relationship_cycle_count:{len(cycles)}")
    source_supported_count = sum(row.get("relationship_status") == "source_supported" for row in relationships)
    if source_supported_count < min_source_supported:
        failures.append(f"source_supported_below_minimum expected>={min_source_supported} actual={source_supported_count}")
    if not anchors:
        warnings.append("no_assembly_anchors_found")
    if not rows:
        warnings.append("no_ipl_rows_found")
    if not relationships:
        warnings.append("no_relationships_found")

    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "inventory_pages": len(inventory),
            "assembly_anchors": len(anchors),
            "ipl_rows": len(rows),
            "relationships": len(relationships),
            "source_supported_relationships": source_supported_count,
            "ambiguous_relationships": sum(row.get("relationship_status") == "ambiguous" for row in relationships),
            "candidate_relationships": sum(row.get("relationship_status") == "candidate" for row in relationships),
            "cycle_count": len(cycles),
            "synthetic_record_count": 0,
            "production_graph_write_count": 0,
        },
        "cycles": cycles,
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "synthetic_records_allowed_in_phase0_3": False,
            "ambiguous_relationships_promoted_to_proof": False,
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_phase0_3(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    metadata_member: str = "metadata.xml",
    page_id_prefix: str = "t_p_120_1176_p",
    document_id: str = "120-1176",
    pilot_pages: str = "342-344,348-349,351,354,363,368",
    ocr_records: str | Path | None = None,
    tesseract_cmd: str = "",
    tesseract_psm: int = 6,
    expected_page_count: int = 509,
    min_source_supported: int = 1,
) -> dict[str, Any]:
    source = CorpusSource(Path(input_path).resolve())
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    inventory, inventory_summary = parse_mets_inventory(
        source,
        metadata_member=metadata_member,
        page_id_prefix=page_id_prefix,
        document_id=document_id,
    )
    by_ordinal = {int(row["page_ordinal"]): row for row in inventory}
    ocr_index = load_ocr_index(ocr_records)
    selected = parse_page_spec(pilot_pages, maximum=len(inventory))

    anchors: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    page_processing: list[dict[str, Any]] = []

    for ordinal in selected:
        page = by_ordinal.get(ordinal)
        if not page:
            continue
        pid = str(page["canonical_page_id"])
        text = ocr_index.get(pid, "")
        method = "ocr_artifact" if text else ""
        if not text and tesseract_cmd:
            text = tesseract_ocr(source, page, tesseract_cmd=tesseract_cmd, psm=tesseract_psm)
            method = "tesseract_direct" if text else ""
        page_anchors = discover_assembly_anchors(pid, text)
        page_rows = reconstruct_ipl_rows(pid, text, page_anchors)
        page_relationships = build_relationships(pid, page_anchors, page_rows)
        anchors.extend(page_anchors)
        rows.extend(page_rows)
        relationships.extend(page_relationships)
        page_processing.append({
            "page_ordinal": ordinal,
            "page_id": pid,
            "tiff_filename": page["tiff_filename"],
            "ocr_method": method or "missing",
            "ocr_char_count": len(text),
            "anchor_count": len(page_anchors),
            "row_count": len(page_rows),
            "relationship_count": len(page_relationships),
        })

    validation = validate_artifacts(
        inventory,
        anchors,
        rows,
        relationships,
        expected_page_count=expected_page_count,
        min_source_supported=min_source_supported,
    )
    answer_key = build_answer_key(relationships)
    graph_bundle = build_graph_bundle(
        inventory,
        relationships,
        document_id=document_id,
        revision=str(inventory_summary.get("document_revision") or ""),
    )

    write_json(output / "trace_net_nha_page_inventory_v1.json", {
        "summary": inventory_summary,
        "records": inventory,
    })
    write_jsonl(output / "trace_net_nha_page_inventory_v1.jsonl", inventory)
    write_json(output / "trace_net_nha_assembly_anchors_v1.json", {"records": anchors})
    write_jsonl(output / "trace_net_nha_assembly_anchors_v1.jsonl", anchors)
    write_json(output / "trace_net_nha_ipl_rows_v1.json", {"records": rows})
    write_jsonl(output / "trace_net_nha_ipl_rows_v1.jsonl", rows)
    write_json(output / "trace_net_nha_relationships_v1.json", {"records": relationships})
    write_jsonl(output / "trace_net_nha_relationships_v1.jsonl", relationships)
    write_json(output / "trace_net_nha_real_answer_key_v1.json", answer_key)
    write_json(output / "trace_net_nha_graph_bundle_v1.json", graph_bundle)
    write_json(output / "trace_net_nha_page_processing_v1.json", {"records": page_processing})
    write_json(output / "trace_net_nha_phase0_3_quality_v1.json", validation)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": validation["quality_status"],
        "input_path": str(source.path),
        "output_dir": str(output),
        "pilot_pages": selected,
        "ocr_artifact_path": str(ocr_records or ""),
        "tesseract_direct_enabled": bool(tesseract_cmd),
        "inventory": inventory_summary,
        "phase_counts": validation["counts"],
        "page_processing": page_processing,
        "failures": validation["failures"],
        "warnings": validation["warnings"],
        "artifacts": sorted(path.name for path in output.glob("trace_net_nha_*.json*")),
    }
    write_json(output / "trace_net_nha_phase0_3_summary_v1.json", summary)
    return summary
