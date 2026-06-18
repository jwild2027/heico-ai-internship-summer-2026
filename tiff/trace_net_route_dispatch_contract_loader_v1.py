from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Union

ROUTE_TABLE = "table"
ROUTE_IMAGE_VISUAL = "image_visual"
ROUTE_NORMAL_TEXT = "normal_text"
ROUTE_BLANK_CANDIDATE = "blank_candidate"
ROUTE_REVIEW = "review"

ROUTE_ORDER = [
    ROUTE_TABLE,
    ROUTE_IMAGE_VISUAL,
    ROUTE_NORMAL_TEXT,
    ROUTE_BLANK_CANDIDATE,
    ROUTE_REVIEW,
]

ROUTE_TO_ALLOWED_FLAG = {
    ROUTE_TABLE: "table_processing_allowed",
    ROUTE_IMAGE_VISUAL: "image_visual_processing_allowed",
    ROUTE_NORMAL_TEXT: "normal_text_processing_allowed",
    ROUTE_BLANK_CANDIDATE: "blank_candidate_processing_allowed",
    ROUTE_REVIEW: "review_processing_required",
}

SCHEMA_VERSION = "trace_net_route_dispatch_contract_loader_v1"
CONTRACT_SCHEMA_VERSION = "trace_net_route_dispatch_processor_contract_v1"

PathLike = Union[str, Path]


def _read_json(path: PathLike) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _page_number_from_any(value: Any) -> Optional[int]:
    page_number = _safe_int(value)
    if page_number is not None:
        return page_number
    if not value:
        return None
    text = str(value)
    # Supports metadata_page_000123 and t_p_120_1176_p000123 style IDs.
    for marker in ("metadata_page_", "_p"):
        if marker in text:
            suffix = text.rsplit(marker, 1)[-1]
            if suffix.isdigit():
                return int(suffix)
    # Last six digits are commonly the rendered page number.
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 6:
        return int(digits[-6:])
    return None


def page_aliases(
    *,
    page_id: Optional[Any] = None,
    source_page_id: Optional[Any] = None,
    page_number: Optional[Any] = None,
) -> List[str]:
    """Return stable aliases used by TRACE-Net routing artifacts.

    This intentionally mirrors the alias policy used by route dispatch coverage
    audit: route cards can be addressed by TRACE-Net page_id, metadata source
    page_id, or page number.
    """
    aliases: List[str] = []
    for value in (page_id, source_page_id):
        if value:
            aliases.append(str(value))

    number = _page_number_from_any(page_number)
    if number is None:
        number = _page_number_from_any(page_id) or _page_number_from_any(source_page_id)
    if number is not None:
        aliases.append(f"metadata_page_{number:06d}")
        aliases.append(f"t_p_120_1176_p{number:06d}")
        aliases.append(str(number))

    return list(dict.fromkeys(alias for alias in aliases if alias))


def _aliases_for_card(card: Mapping[str, Any]) -> List[str]:
    return page_aliases(
        page_id=card.get("page_id"),
        source_page_id=card.get("source_page_id"),
        page_number=card.get("page_number"),
    )


def _cards_from_payload(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    cards = payload.get("processor_contract_cards") or payload.get("route_dispatch_processor_contract_cards") or []
    if not isinstance(cards, list):
        return []
    return [dict(card) for card in cards if isinstance(card, Mapping)]


def _route_allowed_from_card(card: Mapping[str, Any], route: str) -> bool:
    flag = ROUTE_TO_ALLOWED_FLAG.get(route)
    if flag and bool(card.get(flag)):
        return True

    allowed_routes = card.get("allowed_dispatch_routes") or card.get("allowed_processor_routes") or card.get("processor_allowed_routes") or []
    if isinstance(allowed_routes, list) and route in set(str(item) for item in allowed_routes):
        return True

    # Allowlist page entries often have a single route field.
    if str(card.get("route") or "") == route:
        return True
    return False


def _card_is_safe(card: Mapping[str, Any]) -> bool:
    return bool(card.get("safe_for_routing", True)) and not bool(card.get("unsafe_contract_card", False))


@dataclass(frozen=True)
class RouteDispatchContractLookupResult:
    page_key: str
    page_id: Optional[str]
    source_page_id: Optional[str]
    page_number: Optional[int]
    allowed_routes: List[str]
    review_required: bool
    safe_for_routing: bool
    card: Mapping[str, Any]


class RouteDispatchProcessorContract:
    """Read-only helper for downstream processors.

    Downstream modules should call this loader instead of reimplementing route
    dispatch logic. It never grants answer permission and never mutates source
    truth; it only answers whether a page is allowed for a processor route.
    """

    def __init__(self, payload: Mapping[str, Any], contract_path: Optional[PathLike] = None):
        self.payload: Mapping[str, Any] = payload
        self.contract_path = Path(contract_path) if contract_path else None
        self.quality_status = str(payload.get("quality_status") or payload.get("summary", {}).get("quality_status") or "")
        self.schema_version = str(payload.get("schema_version") or "")
        self.summary: Mapping[str, Any] = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
        self.cards: List[Dict[str, Any]] = _cards_from_payload(payload)
        self._by_alias: Dict[str, Dict[str, Any]] = {}
        self._route_to_pages: Dict[str, List[Dict[str, Any]]] = {route: [] for route in ROUTE_ORDER}
        self._index_cards()

    @classmethod
    def load(cls, contract_path: PathLike) -> "RouteDispatchProcessorContract":
        return cls(_read_json(contract_path), contract_path=contract_path)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RouteDispatchProcessorContract":
        return cls(payload)

    def _index_cards(self) -> None:
        for card in self.cards:
            for alias in _aliases_for_card(card):
                self._by_alias.setdefault(alias, card)
            if not _card_is_safe(card):
                continue
            for route in ROUTE_ORDER:
                if _route_allowed_from_card(card, route):
                    self._route_to_pages[route].append(card)

    def get_card(
        self,
        page_key: Optional[Any] = None,
        *,
        page_id: Optional[Any] = None,
        source_page_id: Optional[Any] = None,
        page_number: Optional[Any] = None,
    ) -> Optional[Mapping[str, Any]]:
        aliases = []
        if page_key is not None:
            aliases.extend(page_aliases(page_id=page_key, source_page_id=page_key, page_number=page_key))
        aliases.extend(page_aliases(page_id=page_id, source_page_id=source_page_id, page_number=page_number))
        for alias in aliases:
            card = self._by_alias.get(alias)
            if card:
                return card
        return None

    def require_card(self, page_key: Optional[Any] = None, **kwargs: Any) -> Mapping[str, Any]:
        card = self.get_card(page_key, **kwargs)
        if not card:
            raise KeyError(f"page not found in route dispatch processor contract: {page_key or kwargs}")
        return card

    def is_allowed(self, page_key: Optional[Any], route: str, **kwargs: Any) -> bool:
        if route not in ROUTE_TO_ALLOWED_FLAG:
            raise ValueError(f"unknown route: {route!r}")
        card = self.get_card(page_key, **kwargs)
        if not card or not _card_is_safe(card):
            return False
        return _route_allowed_from_card(card, route)

    def is_table_allowed(self, page_key: Optional[Any] = None, **kwargs: Any) -> bool:
        return self.is_allowed(page_key, ROUTE_TABLE, **kwargs)

    def is_image_visual_allowed(self, page_key: Optional[Any] = None, **kwargs: Any) -> bool:
        return self.is_allowed(page_key, ROUTE_IMAGE_VISUAL, **kwargs)

    def is_normal_text_allowed(self, page_key: Optional[Any] = None, **kwargs: Any) -> bool:
        return self.is_allowed(page_key, ROUTE_NORMAL_TEXT, **kwargs)

    def is_blank_candidate(self, page_key: Optional[Any] = None, **kwargs: Any) -> bool:
        return self.is_allowed(page_key, ROUTE_BLANK_CANDIDATE, **kwargs)

    def is_review_required(self, page_key: Optional[Any] = None, **kwargs: Any) -> bool:
        card = self.get_card(page_key, **kwargs)
        if not card or not _card_is_safe(card):
            return False
        return bool(card.get("review_processing_required") or card.get("review_required") or _route_allowed_from_card(card, ROUTE_REVIEW))

    def allowed_routes(self, page_key: Optional[Any] = None, **kwargs: Any) -> List[str]:
        card = self.get_card(page_key, **kwargs)
        if not card or not _card_is_safe(card):
            return []
        return [route for route in ROUTE_ORDER if _route_allowed_from_card(card, route)]

    def lookup(self, page_key: Optional[Any] = None, **kwargs: Any) -> Optional[RouteDispatchContractLookupResult]:
        card = self.get_card(page_key, **kwargs)
        if not card:
            return None
        page_number = _page_number_from_any(card.get("page_number"))
        return RouteDispatchContractLookupResult(
            page_key=str(page_key or card.get("page_id") or card.get("source_page_id") or page_number),
            page_id=str(card.get("page_id")) if card.get("page_id") else None,
            source_page_id=str(card.get("source_page_id")) if card.get("source_page_id") else None,
            page_number=page_number,
            allowed_routes=self.allowed_routes(card.get("page_id")),
            review_required=self.is_review_required(card.get("page_id")),
            safe_for_routing=_card_is_safe(card),
            card=card,
        )

    def page_cards_for_route(self, route: str) -> List[Mapping[str, Any]]:
        if route not in ROUTE_TO_ALLOWED_FLAG:
            raise ValueError(f"unknown route: {route!r}")
        return list(self._route_to_pages.get(route) or [])

    def page_ids_for_route(self, route: str) -> List[str]:
        ids: List[str] = []
        for card in self.page_cards_for_route(route):
            value = card.get("page_id") or card.get("source_page_id")
            if value:
                ids.append(str(value))
        return ids

    def table_page_ids(self) -> List[str]:
        return self.page_ids_for_route(ROUTE_TABLE)

    def image_visual_page_ids(self) -> List[str]:
        return self.page_ids_for_route(ROUTE_IMAGE_VISUAL)

    def normal_text_page_ids(self) -> List[str]:
        return self.page_ids_for_route(ROUTE_NORMAL_TEXT)

    def blank_candidate_page_ids(self) -> List[str]:
        return self.page_ids_for_route(ROUTE_BLANK_CANDIDATE)

    def review_required_page_ids(self) -> List[str]:
        return self.page_ids_for_route(ROUTE_REVIEW)

    def guard_summary(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "contract_schema_version": self.schema_version,
            "contract_quality_status": self.quality_status,
            "contract_card_count": len(self.cards),
            "alias_count": len(self._by_alias),
            "table_page_count": len(self.table_page_ids()),
            "image_visual_page_count": len(self.image_visual_page_ids()),
            "normal_text_page_count": len(self.normal_text_page_ids()),
            "blank_candidate_page_count": len(self.blank_candidate_page_ids()),
            "review_required_page_count": len(self.review_required_page_ids()),
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        }


def load_route_dispatch_processor_contract(contract_path: PathLike) -> RouteDispatchProcessorContract:
    return RouteDispatchProcessorContract.load(contract_path)


def is_page_allowed_for_route(contract_path: PathLike, page_key: Any, route: str) -> bool:
    return load_route_dispatch_processor_contract(contract_path).is_allowed(page_key, route)
