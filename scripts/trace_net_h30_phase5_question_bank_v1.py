#!/usr/bin/env python3
"""Deterministic 100-question corpus builder for TRACE-Net H30 Phase 5.

This module is evaluation-only. It reads the same graph/V3 truth bundle used by
Grounded-20 and emits a route-balanced benchmark bank without changing runtime
retrieval, ranking, routing, writing, or source truth.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_h30_phase5_question_bank_v1"
STATUS = "TRACE_NET_H30_PHASE5_QUESTION_BANK_V1"
SCHEMA_VERSION = "trace_net_h30_phase5_grounded100_bank_v1"
CONTRACT_ID = "trace_net_h30_phase5_grounded100_contract_v1"

CATEGORY_COUNTS: tuple[tuple[str, int], ...] = (
    ("exact_part", 8),
    ("manufacturer_identifier", 2),
    ("partial_prefix", 3),
    ("partial_contains", 3),
    ("partial_suffix", 2),
    ("partial_family", 2),
    ("safe_general", 2),
    ("nomenclature", 8),
    ("ata_system", 8),
    ("table_ipl", 7),
    ("visual_figure", 7),
    ("procedure", 6),
    ("warning_caution_note", 4),
    ("ocr_recovery", 6),
    ("graph_relationship", 5),
    ("semantic_discovery", 1),
    ("document_navigation", 5),
    ("cross_source_comparison", 4),
    ("contradiction_resolution", 3),
    ("high_degree_aggregation", 3),
    ("authority_eligibility", 4),
    ("multi_question_research", 3),
    ("negative_part", 2),
    ("negative_page", 1),
    ("clarification", 1),
)
EXPECTED_TOTAL = sum(count for _category, count in CATEGORY_COUNTS)

EXPECTED_ROUTE_COUNTS = {
    "exact_identifier_lookup": 12,
    "guided_part_discovery": 10,
    "safe_general_chat": 2,
    "nomenclature_function_search": 8,
    "ata_system_discovery": 8,
    "exact_table_ipl_lookup": 7,
    "visual_figure_callout_lookup": 7,
    "procedure_task_lookup": 6,
    "warning_caution_note_lookup": 4,
    "ocr_scan_recovery": 6,
    "graph_relationship_reasoning": 5,
    "semantic_discovery": 1,
    "document_page_navigation": 6,
    "cross_source_comparison": 4,
    "contradiction_resolution": 3,
    "high_degree_entity_aggregation": 3,
    "authority_eligibility_verification": 4,
    "multi_question_research": 3,
    "clarification_no_evidence": 1,
}

PRIORITY_NOUNS = (
    "PIN", "RING", "LATCH", "COVER", "PANEL", "BRACKET", "FITTING",
    "SCREW", "BOLT", "CLIP", "SEAT", "FASTENER", "RETAINER", "SPRING",
    "WASHER", "ARMREST", "SUPPORT", "HINGE", "TABLE", "LEG",
)
OTHER_IDENTIFIER_RE = re.compile(r"\b[A-Z]{2,}\d{3,}(?:[-./][A-Z0-9]+)+\b", re.I)
TOKEN_RE = re.compile(r"[A-Za-z0-9]{4,}")


def _compact(value: Any, limit: int = 10000) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _page_of(card: Mapping[str, Any]) -> str:
    return str(card.get("page_id") or card.get("source_page_id") or "")


def _route_of(card: Mapping[str, Any]) -> str:
    route = card.get("route")
    if isinstance(route, Mapping):
        return str(route.get("recommended_route_candidate") or route.get("best_route_candidate_before_review") or "")
    return str(route or card.get("recommended_route_candidate") or "")


def _card_blob(card: Mapping[str, Any]) -> str:
    return " ".join(
        _compact(card.get(key), 12000)
        for key in (
            "important_parts", "v2_retrieval_summary", "v2_short_summary",
            "retrieval_profile", "ocr", "v2_role", "v2_subrole",
        )
    )


def _parts_from_card(card: Mapping[str, Any]) -> list[str]:
    # Reuse the common three-section aircraft part format and retain broader
    # manufacturer-style identifiers for the dedicated category.
    values = re.findall(r"\b\d{2,4}-\d{4,6}(?:-\d{3})?\b", _card_blob(card), re.I)
    return list(dict.fromkeys(value.upper() for value in values))


def _other_identifiers(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for card in sorted(cards, key=_page_of):
        pid = _page_of(card)
        blob = _card_blob(card)
        for value in OTHER_IDENTIFIER_RE.findall(blob):
            value = value.upper()
            if value in seen:
                continue
            seen.add(value)
            output.append({"identifier": value, "page_id": pid})
    return output


def _question(
    category: str,
    prompt: str,
    route: str,
    *,
    identifiers: Iterable[str] = (),
    pages: Iterable[str] = (),
    terms: Iterable[str] = (),
    basis: Mapping[str, Any] | None = None,
    negative: bool = False,
    authority_sensitive: bool = False,
    multi_claim: bool = False,
    requires_citation: bool = True,
) -> dict[str, Any]:
    return {
        "category": category,
        "question": prompt,
        "expected_route": route,
        "expected_identifiers": list(dict.fromkeys(str(value) for value in identifiers if str(value))),
        "expected_pages": list(dict.fromkeys(str(value) for value in pages if str(value))),
        "expected_terms": list(dict.fromkeys(str(value) for value in terms if str(value))),
        "source_basis": dict(basis or {}),
        "negative_control": bool(negative),
        "authority_sensitive": bool(authority_sensitive),
        "multi_claim": bool(multi_claim),
        "requires_citation": bool(requires_citation),
    }


def _select_cards(
    cards: Sequence[Mapping[str, Any]],
    predicate,
    count: int,
    *,
    used_pages: set[str] | None = None,
) -> list[Mapping[str, Any]]:
    used_pages = used_pages if used_pages is not None else set()
    selected: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for card in sorted(cards, key=lambda row: (_page_of(row) in used_pages, _page_of(row))):
        pid = _page_of(card)
        if not pid or pid in seen or not predicate(card):
            continue
        selected.append(card)
        seen.add(pid)
        if len(selected) >= count:
            return selected
    # Evaluation generation must remain robust when route metadata is sparse.
    for card in sorted(cards, key=_page_of):
        pid = _page_of(card)
        if not pid or pid in seen:
            continue
        selected.append(card)
        seen.add(pid)
        if len(selected) >= count:
            return selected
    if len(selected) < count:
        raise RuntimeError(f"not_enough_cards requested={count} found={len(selected)}")
    return selected


def _rare_ocr_clues(cards: Sequence[Mapping[str, Any]], count: int) -> list[tuple[str, str]]:
    samples: dict[str, str] = {}
    document_frequency: Counter[str] = Counter()
    for card in cards:
        pid = _page_of(card)
        ocr = card.get("ocr") if isinstance(card.get("ocr"), Mapping) else {}
        sample = _compact(ocr.get("sample_text") or _card_blob(card), 1600)
        if not pid or len(sample) < 30:
            continue
        samples[pid] = sample
        document_frequency.update(set(token.upper() for token in TOKEN_RE.findall(sample)))

    scored: list[tuple[int, str, str]] = []
    for pid, sample in samples.items():
        words = sample.split()
        windows = [words] if len(words) <= 10 else [words[index:index + 10] for index in range(len(words) - 9)]
        best_window: list[str] | None = None
        best_score: int | None = None
        for window in windows:
            phrase = " ".join(window)
            tokens = [token.upper() for token in TOKEN_RE.findall(phrase)]
            score = sum(document_frequency[token] for token in tokens)
            if best_score is None or score < best_score:
                best_score = score
                best_window = window
        if best_window:
            scored.append((int(best_score or 0), pid, " ".join(best_window)))
    scored.sort(key=lambda row: (row[0], row[1]))
    if len(scored) < count:
        raise RuntimeError(f"not_enough_ocr_clues requested={count} found={len(scored)}")
    return [(pid, clue) for _score, pid, clue in scored[:count]]


def _stable_digest(bank: Sequence[Mapping[str, Any]]) -> str:
    blob = json.dumps(list(bank), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_phase5_bank(truth: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create the deterministic route-balanced 100-question bank."""
    parts = [dict(row) for row in truth.get("parts") or [] if isinstance(row, Mapping)]
    cards = [dict(row) for row in truth.get("cards") or [] if isinstance(row, Mapping)]
    ata_pages = {
        str(key): [str(value) for value in values]
        for key, values in (truth.get("ata_pages") or {}).items()
        if isinstance(values, list)
    }
    usable_parts = [
        row for row in parts
        if row.get("part") and row.get("pages") and bool(row.get("source_resolved", True))
    ]
    if len(usable_parts) < 30:
        raise RuntimeError(f"not_enough_grounded_parts found={len(usable_parts)}")
    if len(cards) < 30:
        raise RuntimeError(f"not_enough_page_cards found={len(cards)}")

    bank: list[dict[str, Any]] = []
    part_index = 0

    def next_part(*, nomenclature: bool = False, high_degree: bool = False) -> dict[str, Any]:
        nonlocal part_index
        pool = usable_parts
        if nomenclature:
            pool = [row for row in pool if row.get("nomenclature")]
        if high_degree:
            pool = sorted(pool, key=lambda row: (-len(row.get("pages") or []), str(row.get("part"))))
        if not pool:
            raise RuntimeError("empty_part_pool")
        row = dict(pool[part_index % len(pool)])
        part_index += 1
        return row

    # 8 exact grounded part lookups.
    for _ in range(8):
        row = next_part(nomenclature=True)
        page = dict((row.get("pages") or [{}])[0])
        part = str(row["part"])
        bank.append(_question(
            "exact_part", f"Find part {part} and cite its strongest source page.",
            "exact_identifier_lookup", identifiers=[part], pages=[page.get("page_id", "")],
            terms=row.get("nomenclature") or [], basis={"part": part, "page": page},
        ))

    # 2 manufacturer-style identifiers discovered from page text. Fall back to
    # known nonnumeric document identifiers only when the V3 adapter is sparse.
    manufacturer_ids = _other_identifiers(cards)
    fallback_manufacturer_ids = [
        {"identifier": "MS16562-216", "page_id": "t_p_120_1176_p000455"},
        {"identifier": "PE21052-2", "page_id": "t_p_120_1176_p000075"},
    ]
    # Deduplicate discovered and fallback identifiers before selecting the two
    # benchmark cases. The deployed V3 text may already contain a fallback ID.
    # TRACE_NET_H30_PHASE5_UNIQUE_PROMPTS_V1
    manufacturer_candidates: list[dict[str, str]] = []
    seen_manufacturer_identifiers: set[str] = set()
    for row in manufacturer_ids + fallback_manufacturer_ids:
        identifier = str(row.get("identifier") or "").upper()
        normalized_identifier = _norm(identifier)
        if not normalized_identifier or normalized_identifier in seen_manufacturer_identifiers:
            continue
        seen_manufacturer_identifiers.add(normalized_identifier)
        manufacturer_candidates.append({
            "identifier": identifier,
            "page_id": str(row.get("page_id") or ""),
        })
    if len(manufacturer_candidates) < 2:
        raise RuntimeError(
            f"not_enough_unique_manufacturer_identifiers found={len(manufacturer_candidates)}"
        )
    for row in manufacturer_candidates[:2]:
        identifier = row["identifier"]
        bank.append(_question(
            "manufacturer_identifier",
            f"Find manufacturer-style identifier {identifier} and show the cited source page and nomenclature.",
            "exact_identifier_lookup", identifiers=[identifier], pages=[row.get("page_id", "")],
            basis=row,
        ))

    # 10 partial/family discovery questions. Real manuals contain many suffix
    # variants in the same family, so two grounded targets may legitimately yield
    # the same clue. Use deterministic wording variants to keep question text
    # unique without inventing identifiers, pages, or retrieval expectations.
    # TRACE_NET_H30_PHASE5_UNIQUE_DISCOVERY_PROMPTS_V1
    partial_specs = (
        ("partial_prefix", 3, "starts with"),
        ("partial_contains", 3, "contains"),
        ("partial_suffix", 2, "ends with"),
        ("partial_family", 2, "belongs to the family"),
    )
    partial_prompt_templates = (
        "I only remember that the part number {phrase} {clue}. Show matching candidates and cited source pages.",
        "Search for part numbers that {phrase} {clue}. Return distinct candidates with their cited source pages.",
        "Use the partial clue {clue}: the part number {phrase} it. Separate every candidate by cited source page.",
    )
    for category, count, phrase in partial_specs:
        for variant_index in range(count):
            row = next_part()
            part = str(row["part"])
            normalized = _norm(part)
            if category == "partial_prefix":
                clue = normalized[:8]
            elif category == "partial_contains":
                clue = normalized[max(1, len(normalized) // 3):max(6, len(normalized) // 3 + 5)]
            elif category == "partial_suffix":
                clue = normalized[-3:]
            else:
                clue = "-".join(part.split("-")[:2])
            page = dict((row.get("pages") or [{}])[0])
            prompt = partial_prompt_templates[variant_index].format(
                phrase=phrase,
                clue=clue,
            )
            bank.append(_question(
                category,
                prompt,
                "guided_part_discovery", identifiers=[part], pages=[page.get("page_id", "")],
                basis={
                    "part": part,
                    "clue": clue,
                    "mode": category,
                    "prompt_variant": variant_index + 1,
                },
            ))

    # 2 safe general controls.
    bank.extend([
        _question("safe_general", "Hello. Briefly explain what TRACE-Net can help search.", "safe_general_chat", requires_citation=False),
        _question("safe_general", "What kinds of aircraft-manual questions can you help organize?", "safe_general_chat", requires_citation=False),
    ])

    # 8 nomenclature questions from grounded names.
    noun_rows: list[tuple[str, dict[str, Any]]] = []
    seen_nouns: set[str] = set()
    for noun in PRIORITY_NOUNS:
        for row in usable_parts:
            names = " ".join(str(value) for value in row.get("nomenclature") or []).upper()
            if noun in names and noun not in seen_nouns:
                noun_rows.append((noun, row)); seen_nouns.add(noun); break
    for row in usable_parts:
        if len(noun_rows) >= 8:
            break
        for name in row.get("nomenclature") or []:
            for noun in re.findall(r"[A-Z]{4,}", str(name).upper()):
                if noun in {"ASSY", "ASSEMBLY", "SINGLE", "PASSENGER", "WITH"} or noun in seen_nouns:
                    continue
                noun_rows.append((noun, row)); seen_nouns.add(noun); break
            if len(noun_rows) >= 8:
                break
    if len(noun_rows) < 8:
        raise RuntimeError(f"not_enough_nomenclature_terms found={len(noun_rows)}")
    for noun, row in noun_rows[:8]:
        page = dict((row.get("pages") or [{}])[0])
        bank.append(_question(
            "nomenclature",
            f"Find the {noun.lower()} in the document set. Show the strongest part candidates and connected source pages.",
            "nomenclature_function_search", identifiers=[str(row["part"])], pages=[page.get("page_id", "")],
            terms=[noun], basis={"part": row["part"], "nomenclature": row.get("nomenclature")},
        ))

    # 8 ATA system searches. The deployed corpus may expose fewer than eight
    # distinct ATA codes, so deterministically reuse grounded codes with unique
    # evidence objectives instead of inventing codes or aborting bank creation.
    # TRACE_NET_H30_PHASE5_ATA_REUSE_V1
    atas = [
        (
            ata,
            list(dict.fromkeys(page for page in pages if str(page).strip())),
        )
        for ata, pages in sorted(
            ata_pages.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
        if pages
    ]
    if not atas:
        raise RuntimeError("no_grounded_ata_codes")

    ata_prompt_templates = (
        "Find the relevant parts and source pages in ATA {ata}. Summarize the strongest available evidence.",
        "Review ATA {ata} and list the strongest indexed part and source-page evidence.",
        "For ATA {ata}, identify the cited source pages and the most relevant part or nomenclature leads.",
        "Summarize indexed page coverage and the strongest grounded technical evidence for ATA {ata}.",
        "Which parts and cited source pages are most relevant to ATA {ata}? Keep guidance separate from proof.",
        "Recheck ATA {ata} with emphasis on distinct source pages and grounded part evidence.",
        "Build a source-location summary for ATA {ata}, including relevant part and page leads.",
        "Consolidate the strongest available parts and source-page evidence for ATA {ata}.",
    )
    for ata_index in range(8):
        ata, pages = atas[ata_index % len(atas)]
        bank.append(_question(
            "ata_system",
            ata_prompt_templates[ata_index].format(ata=ata),
            "ata_system_discovery",
            pages=pages[:8],
            terms=[ata],
            basis={
                "ata": ata,
                "pages": pages[:20],
                "variant": ata_index + 1,
                "available_ata_code_count": len(atas),
                "ata_code_reused": ata_index >= len(atas),
            },
        ))
    used_pages: set[str] = set()
    table_cards = _select_cards(
        cards,
        lambda card: _route_of(card) in {"detailed_parts_list", "table_or_index"}
        or any(token in _card_blob(card).lower() for token in ("illustrated parts", "parts list", "table", "item")),
        7,
        used_pages=used_pages,
    )
    for card in table_cards:
        pid = _page_of(card); used_pages.add(pid); card_parts = _parts_from_card(card)
        prompt = f"Locate part {card_parts[0]} in the IPL table and preserve same-row relationships." if card_parts else f"Show the IPL/table content on page {pid}."
        bank.append(_question(
            "table_ipl", prompt, "exact_table_ipl_lookup", identifiers=card_parts[:1], pages=[pid],
            basis={"page": pid, "route": _route_of(card), "source_path": card.get("source_path")},
        ))

    visual_cards = _select_cards(
        cards,
        lambda card: _route_of(card) in {"image_visual_diagram", "mixed_text_and_figure"}
        or any(token in _card_blob(card).lower() for token in ("figure", "diagram", "illustration")),
        7,
        used_pages=used_pages,
    )
    for card in visual_cards:
        pid = _page_of(card); used_pages.add(pid); card_parts = _parts_from_card(card)
        prompt = f"Show the diagram for part {card_parts[0]} on page {pid} and report only explicit labels or callouts." if card_parts else f"Show the diagram on page {pid} and report only explicit labels or callouts."
        bank.append(_question(
            "visual_figure", prompt, "visual_figure_callout_lookup", identifiers=card_parts[:1], pages=[pid],
            basis={"page": pid, "route": _route_of(card), "source_path": card.get("source_path")},
        ))

    procedure_cards = _select_cards(
        cards,
        lambda card: _route_of(card) == "procedure_or_description"
        or any(token in _card_blob(card).lower() for token in ("procedure", "remove", "install", "adjust")),
        6,
        used_pages=used_pages,
    )
    for card in procedure_cards:
        pid = _page_of(card); used_pages.add(pid)
        bank.append(_question(
            "procedure", f"What procedure is described on page {pid}? Preserve the readable step sequence and uncertainty.",
            "procedure_task_lookup", pages=[pid], basis={"page": pid, "route": _route_of(card), "source_path": card.get("source_path")},
        ))

    warning_cards = _select_cards(
        cards,
        lambda card: any(token in _card_blob(card).lower() for token in ("warning", "caution", "note")),
        4,
        used_pages=used_pages,
    )
    for card in warning_cards:
        pid = _page_of(card); used_pages.add(pid)
        bank.append(_question(
            "warning_caution_note", f"What warning, caution, or note is explicitly present on page {pid}? Cite the page and do not invent one.",
            "warning_caution_note_lookup", pages=[pid], basis={"page": pid, "source_path": card.get("source_path")},
        ))

    for pid, clue in _rare_ocr_clues(cards, 6):
        bank.append(_question(
            "ocr_recovery",
            f"Locate the scanned page containing this OCR clue: '{clue}'. Reconstruct surrounding text or table relationships and report uncertainty.",
            "ocr_scan_recovery", pages=[pid], terms=[clue], basis={"page": pid, "clue": clue, "scan_quality_assumed": False},
        ))

    # 5 graph relationships.
    for _ in range(5):
        row = next_part(nomenclature=True)
        page = dict((row.get("pages") or [{}])[0]); part = str(row["part"])
        bank.append(_question(
            "graph_relationship", f"What assembly or explicit graph relationship is connected to part {part}?",
            "graph_relationship_reasoning", identifiers=[part], pages=[page.get("page_id", "")],
            terms=row.get("nomenclature") or [], basis={"part": part, "page": page},
        ))

    bank.append(_question(
        "semantic_discovery", "Find pages about corrosion prevention topics and summarize the best source-location leads.",
        "semantic_discovery", terms=["corrosion"], basis={"topic": "corrosion prevention"},
    ))

    nav_cards = _select_cards(cards, lambda _card: True, 5, used_pages=used_pages)
    for card in nav_cards:
        pid = _page_of(card); used_pages.add(pid)
        bank.append(_question(
            "document_navigation", f"Open page {pid} and explain what indexed content it contains.",
            "document_page_navigation", pages=[pid], basis={"page": pid, "source_path": card.get("source_path")},
        ))

    comparison_cards = _select_cards(cards, lambda _card: True, 8, used_pages=used_pages)
    for index in range(0, 8, 2):
        left, right = comparison_cards[index], comparison_cards[index + 1]
        left_pid, right_pid = _page_of(left), _page_of(right)
        bank.append(_question(
            "cross_source_comparison",
            f"Compare indexed pages {left_pid} and {right_pid} for shared and different technical content. Keep each claim tied to its source.",
            "cross_source_comparison", pages=[left_pid, right_pid], basis={"left_page": left_pid, "right_page": right_pid},
            multi_claim=True,
        ))

    for _ in range(3):
        left = next_part(nomenclature=True); right = next_part(nomenclature=True)
        left_page = dict((left.get("pages") or [{}])[0]); right_page = dict((right.get("pages") or [{}])[0])
        bank.append(_question(
            "contradiction_resolution",
            f"Sources for parts {left['part']} and {right['part']} may conflict. Identify only explicit contradictions and preserve both source positions.",
            "contradiction_resolution", identifiers=[left["part"], right["part"]],
            pages=[left_page.get("page_id", ""), right_page.get("page_id", "")],
            basis={"left": left, "right": right}, multi_claim=True,
        ))

    for _ in range(3):
        row = next_part(high_degree=True); pages = [str(page.get("page_id") or "") for page in row.get("pages") or []]
        bank.append(_question(
            "high_degree_aggregation", f"Show every indexed document page mentioning part {row['part']}. Report coverage and avoid silently truncating the result set.",
            "high_degree_entity_aggregation", identifiers=[row["part"]], pages=pages[:12],
            basis={"part": row["part"], "known_page_count": len(pages), "pages": pages[:50]},
        ))

    for _ in range(4):
        left = next_part(nomenclature=True); right = next_part(nomenclature=True)
        bank.append(_question(
            "authority_eligibility",
            f"Is part {left['part']} an approved replacement or interchangeable with {right['part']}? Require explicit authority and effectivity evidence.",
            "authority_eligibility_verification", identifiers=[left["part"], right["part"]],
            basis={"candidate": left["part"], "reference": right["part"]}, authority_sensitive=True,
        ))

    for _ in range(3):
        row = next_part(nomenclature=True); page = dict((row.get("pages") or [{}])[0])
        bank.append(_question(
            "multi_question_research",
            f"Find part {row['part']}, identify its strongest source page, and determine whether the indexed evidence proves approval or effectivity.",
            "multi_question_research", identifiers=[row["part"]], pages=[page.get("page_id", "")],
            basis={"part": row["part"], "page": page}, authority_sensitive=True, multi_claim=True,
        ))

    bank.extend([
        _question("negative_part", "Find part 999-99999-999.", "exact_identifier_lookup", identifiers=["999-99999-999"], negative=True),
        _question("negative_part", "Find part 888-88888-888 and cite the source page.", "exact_identifier_lookup", identifiers=["888-88888-888"], negative=True),
        _question("negative_page", "Open page t_p_120_1176_p999999 and explain what it contains.", "document_page_navigation", pages=["t_p_120_1176_p999999"], negative=True),
        _question("clarification", "Can you help me identify the component?", "clarification_no_evidence", requires_citation=False),
    ])

    if len(bank) != EXPECTED_TOTAL:
        raise AssertionError(f"phase5_bank_size expected={EXPECTED_TOTAL} actual={len(bank)}")
    for index, item in enumerate(bank, 1):
        item["question_id"] = f"q{index:03d}"
        item["ordinal"] = index
        item["schema_version"] = SCHEMA_VERSION
        item["contract_id"] = CONTRACT_ID
    validation = validate_phase5_bank(bank)
    if not validation["accepted"]:
        raise AssertionError("phase5_bank_validation_failed: " + ", ".join(validation["failures"]))
    return bank


def validate_phase5_bank(bank: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    category_counts = Counter(str(item.get("category") or "") for item in bank)
    route_counts = Counter(str(item.get("expected_route") or "") for item in bank)
    expected_categories = dict(CATEGORY_COUNTS)
    ids = [str(item.get("question_id") or "") for item in bank]
    questions = [re.sub(r"\s+", " ", str(item.get("question") or "")).strip().casefold() for item in bank]

    if len(bank) != EXPECTED_TOTAL:
        failures.append(f"question_count:{len(bank)}")
    if dict(category_counts) != expected_categories:
        failures.append("category_distribution_mismatch")
    if dict(route_counts) != EXPECTED_ROUTE_COUNTS:
        failures.append("route_distribution_mismatch")
    if len(ids) != len(set(ids)) or ids != [f"q{index:03d}" for index in range(1, len(bank) + 1)]:
        failures.append("question_ids_invalid")
    if len(questions) != len(set(questions)):
        failures.append("duplicate_question_text")
    for item in bank:
        if not str(item.get("question") or "").strip():
            failures.append("empty_question")
        if not str(item.get("expected_route") or "").strip():
            failures.append("missing_expected_route")
        if item.get("negative_control") and item.get("authority_sensitive"):
            failures.append("negative_authority_contract_conflict")
    return {
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "accepted": not failures,
        "question_count": len(bank),
        "category_counts": dict(category_counts),
        "expected_category_counts": expected_categories,
        "route_counts": dict(route_counts),
        "expected_route_counts": dict(EXPECTED_ROUTE_COUNTS),
        "bank_sha256": _stable_digest(bank),
        "failures": list(dict.fromkeys(failures)),
    }


def bank_document(bank: Sequence[Mapping[str, Any]], truth: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_phase5_bank(bank)
    return {
        "module": MODULE,
        "status": STATUS,
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "quality_status": validation["quality_status"],
        "question_count": len(bank),
        "category_counts": validation["category_counts"],
        "route_counts": validation["route_counts"],
        "bank_sha256": validation["bank_sha256"],
        "artifact_counts": dict(truth.get("counts") or {}),
        "artifact_paths": dict(truth.get("paths") or {}),
        "questions": list(bank),
    }


__all__ = [
    "MODULE", "STATUS", "SCHEMA_VERSION", "CONTRACT_ID", "CATEGORY_COUNTS",
    "EXPECTED_TOTAL", "EXPECTED_ROUTE_COUNTS", "build_phase5_bank",
    "validate_phase5_bank", "bank_document",
]
