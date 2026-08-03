"""Install TRACE-Net Engram Skill Shadow v1 into runtime classes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Mapping

from tiff.trace_net_engram_skill_shadow_v1 import (
    DEFAULT_LIBRARY_PATH,
    attach_engram_skill_shadow,
    load_json,
    validate_skill_library,
)


MODULE = "trace_net_h30_engram_skill_shadow_v1"


def _enabled() -> bool:
    return str(
        os.environ.get("TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED", "1")
    ).strip().lower() not in {"0", "false", "no", "off"}


def _library_path() -> Path:
    return Path(
        os.environ.get(
            "TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH",
            str(DEFAULT_LIBRARY_PATH),
        )
    )


def _max_skills() -> int:
    try:
        value = int(
            os.environ.get(
                "TRACE_NET_H30_ENGRAM_SKILL_SHADOW_MAX_SKILLS",
                "3",
            )
        )
    except ValueError:
        value = 3
    return max(1, min(5, value))


def _extract_query(namespace: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    extractor = namespace.get("extract_latest_user")
    if callable(extractor):
        try:
            return str(extractor(payload) or "")
        except Exception:
            pass
    for key in ("query", "question", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _stage(namespace: Mapping[str, Any]) -> str:
    module_name = str(namespace.get("MODULE") or "")
    if "full_gemma" in module_name:
        return "final_answer_writer"
    return "cognitive_pre_writer"


def _library_health() -> Dict[str, Any]:
    path = _library_path()
    try:
        library = load_json(path)
        if not isinstance(library, Mapping):
            library = {}
        validation = validate_skill_library(library)
        return {
            "enabled": _enabled(),
            "quality_status": validation.get("quality_status"),
            "library_path": str(path),
            "skill_card_count": validation.get("skill_card_count"),
            "error_count": validation.get("error_count"),
            "errors": validation.get("errors") or [],
            "shadow_only": True,
            "applied_to_answer": False,
            "applied_to_route": False,
            "applied_to_retrieval": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "write_attempt_count": 0,
        }
    except Exception as exc:
        return {
            "enabled": _enabled(),
            "quality_status": "FAIL",
            "library_path": str(path),
            "error": f"{type(exc).__name__}: {exc}",
            "shadow_only": True,
            "applied_to_answer": False,
            "applied_to_route": False,
            "applied_to_retrieval": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "write_attempt_count": 0,
        }


def install_engram_skill_shadow(namespace: Dict[str, Any]) -> None:
    runtime_class = namespace.get("CognitiveRuntime") or namespace.get("Runtime")
    if runtime_class is None:
        raise RuntimeError("TRACE-Net Engram skill shadow could not find runtime class")
    if getattr(runtime_class, "_trace_net_engram_skill_shadow_v1_installed", False):
        return

    original_process = runtime_class.process
    original_health = runtime_class.health
    stage = _stage(namespace)

    def process(self, payload):
        current = original_process(self, payload)
        if not isinstance(current, Mapping):
            return current
        if not _enabled():
            output = dict(current)
            output["engram_skill_shadow"] = {
                "quality_status": "DISABLED",
                "stage": stage,
                "shadow_applied_to_answer": False,
                "shadow_applied_to_route": False,
                "shadow_applied_to_retrieval": False,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
            output["engram_skill_shadow_mode"] = False
            return output
        return attach_engram_skill_shadow(
            current,
            query=_extract_query(namespace, payload),
            stage=stage,
            library_path=_library_path(),
            max_skills=_max_skills(),
        )

    def health(self):
        current = original_health(self)
        if not isinstance(current, Mapping):
            return current
        output = dict(current)
        output["engram_skill_shadow"] = _library_health()
        output["engram_skill_shadow_enabled"] = _enabled()
        output["engram_skill_shadow_fail_open"] = True
        output["engram_skill_shadow_changes_current_answer"] = False
        output["engram_skill_shadow_changes_current_route"] = False
        output["engram_skill_shadow_changes_current_retrieval"] = False
        return output

    runtime_class.process = process
    runtime_class.health = health
    runtime_class._trace_net_engram_skill_shadow_v1_installed = True
