"""API contract tests for the TIFF FastAPI boundary.

This module intentionally supports both live HTTP tests and in-process
FastAPI tests. The in-process mode is preferred for quality-gate runs because
it does not require a separate uvicorn process to be running.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import time

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT = Path("local_data/api/api_contract_results.json")


@dataclass(frozen=True)
class ApiContractCase:
    case_id: str
    method: str
    path: str
    description: str
    params: Optional[Mapping[str, Any]] = None
    json_body: Optional[Mapping[str, Any]] = None
    expected_text: Tuple[str, ...] = ()
    slow: bool = False


@dataclass
class ApiContractResult:
    case_id: str
    status: str
    elapsed_seconds: float
    http_status: Optional[int] = None
    error: Optional[str] = None
    missing_expected_text: Optional[List[str]] = None
    response_preview: Optional[str] = None
    slow: bool = False


def default_contract_cases(include_slow: bool = False) -> List[ApiContractCase]:
    cases = [
        ApiContractCase(
            case_id="status_endpoint",
            method="GET",
            path="/status",
            description="Status endpoint returns backend/API readiness.",
            expected_text=("status",),
        ),
        ApiContractCase(
            case_id="organization_summary_endpoint",
            method="GET",
            path="/organization/summary",
            description="Organization summary endpoint returns graph/export counts.",
            expected_text=("pages",),
        ),
        ApiContractCase(
            case_id="part_lookup_120_37313_001",
            method="GET",
            path="/organization/parts/120-37313-001",
            description="Part lookup returns canonical nomenclature and page evidence.",
            expected_text=("120-37313-001", "HOLDER, MAGAZINE"),
        ),
        ApiContractCase(
            case_id="page_lookup_000083",
            method="GET",
            path="/organization/pages/t_p_120_1176_p000083",
            description="Page lookup returns source and context metadata.",
            expected_text=("t_p_120_1176_p000083", "source"),
        ),
        ApiContractCase(
            case_id="ata_lookup_25_21_00",
            method="GET",
            path="/organization/ata/25-21-00",
            description="ATA lookup returns pages/source evidence for the section.",
            expected_text=("25-21-00",),
        ),
        ApiContractCase(
            case_id="trace_part_120_37313_001",
            method="GET",
            path="/trace/part/120-37313-001",
            description="Part trace resolves to source-linked/context pages.",
            expected_text=("120-37313-001", "HOLDER, MAGAZINE", "HAS_CONTEXT"),
        ),
        ApiContractCase(
            case_id="trace_page_000083",
            method="GET",
            path="/trace/page/t_p_120_1176_p000083",
            description="Page trace resolves document, ATA, source, context, and parts.",
            expected_text=("t_p_120_1176_p000083", "HAS_CONTEXT"),
        ),
        ApiContractCase(
            case_id="trace_vector_payload_000495",
            method="GET",
            path="/trace/vector",
            description="Simulated vector payload resolves page_id through the graph.",
            params={
                "page_id": "t_p_120_1176_p000495",
                "chunk_id": "chunk_t_p_120_1176_p000495_001",
                "score": "0.635",
            },
            expected_text=("t_p_120_1176_p000495", "Qdrant"),
        ),
        ApiContractCase(
            case_id="ask_exact_part_120_37313_001",
            method="POST",
            path="/ask",
            description="Ask endpoint answers an exact part lookup with source-backed evidence.",
            json_body={"question": "What is part number 120-37313-001?", "timeout_seconds": 120},
            expected_text=("120-37313-001", "HOLDER, MAGAZINE"),
        ),
        ApiContractCase(
            case_id="feedback_round_trip",
            method="POST",
            path="/feedback",
            description="Feedback endpoint accepts a user rating/comment record.",
            json_body={
                "question": "What is part number 120-37313-001?",
                "answer": "120-37313-001 is listed as HOLDER, MAGAZINE.",
                "rating": "up",
                "category": "useful",
                "reason": "Correct part name and source evidence shown.",
            },
            expected_text=(),
        ),
        ApiContractCase(
            case_id="feedback_summary_endpoint",
            method="GET",
            path="/feedback/summary",
            description="Feedback summary endpoint returns stored feedback counts.",
            expected_text=("feedback",),
        ),
    ]
    if include_slow:
        cases.append(
            ApiContractCase(
                case_id="slow_ask_passenger_seat_back_summary",
                method="POST",
                path="/ask",
                description="Slow RAG/LLM summary endpoint still returns source-backed answer.",
                json_body={
                    "question": "Summarize passenger seat back crack reinforcement using source evidence.",
                    "timeout_seconds": 180,
                },
                expected_text=("Passenger", "Sources"),
                slow=True,
            )
        )
    return cases


def _preview(text: str, limit: int = 600) -> str:
    clean = " ".join(str(text).split())
    return clean[:limit]


def _serialize_response_body(body: Any) -> str:
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False, sort_keys=True)
    return str(body)


def run_live_case(case: ApiContractCase, base_url: str = DEFAULT_BASE_URL, timeout_seconds: int = 180) -> ApiContractResult:
    start = time.perf_counter()
    url = base_url.rstrip("/") + case.path
    if case.params:
        url += "?" + urlencode({k: str(v) for k, v in case.params.items()})
    data = None
    headers = {"Accept": "application/json"}
    if case.json_body is not None:
        data = json.dumps(case.json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=case.method.upper())
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = int(getattr(response, "status", response.getcode()))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return ApiContractResult(
            case_id=case.case_id,
            status="fail",
            elapsed_seconds=time.perf_counter() - start,
            http_status=exc.code,
            error=str(exc),
            response_preview=_preview(raw),
            slow=case.slow,
        )
    except (URLError, OSError, TimeoutError) as exc:
        return ApiContractResult(
            case_id=case.case_id,
            status="fail",
            elapsed_seconds=time.perf_counter() - start,
            http_status=None,
            error=str(exc),
            slow=case.slow,
        )
    body_text = raw
    missing = [needle for needle in case.expected_text if needle and needle not in body_text]
    ok_status = 200 <= status_code < 400
    return ApiContractResult(
        case_id=case.case_id,
        status="pass" if ok_status and not missing else "fail",
        elapsed_seconds=time.perf_counter() - start,
        http_status=status_code,
        missing_expected_text=missing or None,
        response_preview=_preview(body_text),
        slow=case.slow,
    )


def run_in_process_case(case: ApiContractCase, timeout_seconds: int = 180) -> ApiContractResult:
    start = time.perf_counter()
    try:
        from fastapi.testclient import TestClient
        from apps.api.tiff_api import app
    except Exception as exc:  # pragma: no cover - import failure is environment-specific
        return ApiContractResult(
            case_id=case.case_id,
            status="fail",
            elapsed_seconds=time.perf_counter() - start,
            error=f"Could not import FastAPI app/TestClient: {exc}",
            slow=case.slow,
        )
    try:
        with TestClient(app) as client:
            method = case.method.upper()
            if method == "GET":
                response = client.get(case.path, params=dict(case.params or {}), timeout=timeout_seconds)
            elif method == "POST":
                response = client.post(case.path, json=dict(case.json_body or {}), timeout=timeout_seconds)
            else:
                raise ValueError(f"Unsupported method: {case.method}")
            status_code = response.status_code
            try:
                body: Any = response.json()
            except Exception:
                body = response.text
    except Exception as exc:
        return ApiContractResult(
            case_id=case.case_id,
            status="fail",
            elapsed_seconds=time.perf_counter() - start,
            error=str(exc),
            slow=case.slow,
        )
    body_text = _serialize_response_body(body)
    missing = [needle for needle in case.expected_text if needle and needle not in body_text]
    ok_status = 200 <= status_code < 400
    return ApiContractResult(
        case_id=case.case_id,
        status="pass" if ok_status and not missing else "fail",
        elapsed_seconds=time.perf_counter() - start,
        http_status=status_code,
        missing_expected_text=missing or None,
        response_preview=_preview(body_text),
        slow=case.slow,
    )


def run_api_contract_tests(
    *,
    base_url: str = DEFAULT_BASE_URL,
    in_process: bool = False,
    include_slow: bool = False,
    case_ids: Optional[Iterable[str]] = None,
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    selected = default_contract_cases(include_slow=include_slow)
    requested = set(case_ids or [])
    if requested:
        selected = [case for case in selected if case.case_id in requested]
    results: List[ApiContractResult] = []
    total_start = time.perf_counter()
    for case in selected:
        if in_process:
            result = run_in_process_case(case, timeout_seconds=timeout_seconds)
        else:
            result = run_live_case(case, base_url=base_url, timeout_seconds=timeout_seconds)
        results.append(result)
    elapsed = time.perf_counter() - total_start
    pass_count = sum(1 for r in results if r.status == "pass")
    fail_count = sum(1 for r in results if r.status != "pass")
    slow_cases = sum(1 for r in results if r.slow)
    slow_pass = sum(1 for r in results if r.slow and r.status == "pass")
    return {
        "status": "ok" if fail_count == 0 else "fail",
        "mode": "in_process" if in_process else "live_http",
        "mode_label": "in-process" if in_process else "live HTTP",
        "base_url": base_url,
        "total": len(results),
        "pass": pass_count,
        "fail": fail_count,
        "status_counts": {"pass": pass_count, "fail": fail_count},
        "slow_cases": slow_cases,
        "slow_pass": slow_pass,
        "elapsed_seconds": elapsed,
        "cases": [asdict(r) for r in results],
        "case_results": [asdict(r) for r in results],
    }


def write_contract_report(report: Mapping[str, Any], output_path: Path = DEFAULT_OUTPUT) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def case_ids(include_slow: bool = False) -> List[str]:
    return [case.case_id for case in default_contract_cases(include_slow=include_slow)]
