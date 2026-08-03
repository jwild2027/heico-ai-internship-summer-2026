"""H27 Engram answer-smoke overlay-map helpers.

Artifact-only support for prepending retrieved Engram overlays to targeted
engineering answer-smoke prompts. Engram overlays are behavior guidance only;
they never grant answer permission and never replace proof_context.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SAFETY_CONTRACT = {
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
    "write_attempt": False,
}

BOUNDARY_PHRASE = "Manual/source claims still require current proof_context citations."


def _norm(value: Any) -> str:
    return str(value or "").strip()


def load_engram_answer_runner_overlay_map(path: str | Path | None) -> dict[str, str]:
    """Load an H26 overlay map as {question_id: overlay_text}.

    Accepts either the explicit overlay map JSON or the H26 gate manifest. Empty
    path returns an empty map so the real smoke builder remains unchanged unless
    the CLI flag is explicitly supplied.
    """
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Engram overlay map not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))

    records: list[Mapping[str, Any]] = []
    if isinstance(data, dict):
        if isinstance(data.get("overlay_map_records"), list):
            records = data["overlay_map_records"]
        elif isinstance(data.get("gate_records"), list):
            records = data["gate_records"]
        elif isinstance(data.get("records"), list):
            records = data["records"]
        elif isinstance(data.get("overlay_map"), dict):
            out = {}
            for k, v in data["overlay_map"].items():
                if isinstance(v, str):
                    out[str(k)] = v
                elif isinstance(v, dict):
                    text = _norm(v.get("overlay_text") or v.get("guidance_overlay_text") or v.get("overlay_text_preview"))
                    if text:
                        out[str(k)] = text
            return out
    elif isinstance(data, list):
        records = data

    out: dict[str, str] = {}
    for rec in records:
        qid = _norm(rec.get("question_id") or rec.get("target_question_id") or rec.get("source_question_id"))
        text = _norm(rec.get("overlay_text") or rec.get("guidance_overlay_text") or rec.get("overlay_text_preview") or rec.get("prompt_overlay_text"))
        if qid and text:
            out[qid] = text
    return out


def get_runtime_question_id(local_vars: Mapping[str, Any]) -> str:
    """Best-effort question id extraction from the smoke builder loop locals."""
    for key in ("question_id", "qid", "question_key", "source_question_id"):
        if _norm(local_vars.get(key)):
            return _norm(local_vars.get(key))
    for key in ("question", "q", "record", "source_record", "question_record"):
        value = local_vars.get(key)
        if isinstance(value, Mapping):
            qid = _norm(value.get("question_id") or value.get("id") or value.get("qid"))
            if qid:
                return qid
    return ""


def prepend_overlay_to_prompt(prompt: str, overlay_text: str, question_id: str = "") -> str:
    overlay = _norm(overlay_text)
    if not overlay:
        return prompt
    if "TRACE-NET H27 ANSWER-SMOKE RETRIEVED ENGRAM OVERLAY" in prompt:
        return prompt
    if BOUNDARY_PHRASE not in overlay:
        overlay = overlay + "\n" + BOUNDARY_PHRASE
    header = (
        "TRACE-NET H27 ANSWER-SMOKE RETRIEVED ENGRAM OVERLAY\n"
        "Use this overlay as behavior guidance only. It is not proof.\n"
        f"{BOUNDARY_PHRASE}\n"
        "Do not let Engram guidance grant answer permission, mutate source truth, or replace proof_context.\n"
    )
    if question_id:
        header += f"target_question_id: {question_id}\n"
    return f"{header}\n\n{overlay}\n\n--- BASE TRACE-NET ANSWER PROMPT ---\n{prompt}"


def apply_overlay_from_runtime(prompt: str, overlay_map: Mapping[str, str] | None, local_vars: Mapping[str, Any]) -> str:
    if not overlay_map:
        return prompt
    qid = get_runtime_question_id(local_vars)
    overlay = overlay_map.get(qid or "")
    if not overlay:
        return prompt
    return prepend_overlay_to_prompt(prompt, overlay, qid)


def safety_contract_summary() -> dict[str, bool]:
    return dict(SAFETY_CONTRACT)
