#!/usr/bin/env python3
"""Preservation-first overlay for the H30 constrained Gemma writer.

The Phase 3 Answer is already source-validated. This overlay gives Gemma a much
smaller serialization task: reproduce those exact Answer lines in the existing
strict JSON schema. Evidence and Limits remain deterministic and are never
model-authored. Existing validation and deterministic fallback remain unchanged.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from typing import Any, Dict, Mapping, MutableMapping

MODULE = "trace_net_h30_phase19_preservation_writer_v1"
STATUS = "TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_V1"
PATCH_ID = "trace_net_h30_phase19_preservation_writer_v1"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def enabled() -> bool:
    return _bool_env("TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED", False)


def max_tokens() -> int:
    try:
        value = int(str(os.environ.get("TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS", "384")).strip())
    except (TypeError, ValueError):
        value = 384
    return max(128, min(1024, value))


def canonical_answer_object(packet: Mapping[str, Any], output_schema_version: str) -> Dict[str, Any]:
    sections = packet.get("deterministic_sections") if isinstance(packet.get("deterministic_sections"), Mapping) else {}
    lines = [str(value) for value in (sections.get("answer") or []) if str(value).strip()]
    return {"schema_version": output_schema_version, "answer": lines}


def answer_digest(packet: Mapping[str, Any], output_schema_version: str) -> str:
    payload = json.dumps(
        canonical_answer_object(packet, output_schema_version),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_preservation_prompt(packet: Mapping[str, Any], output_schema_version: str) -> str:
    exact = canonical_answer_object(packet, output_schema_version)
    exact_json = json.dumps(exact, ensure_ascii=False, indent=2)
    route = str(packet.get("route") or "")
    required = [str(value) for value in (packet.get("required_answer_phrases") or [])]
    return f"""You are TRACE-Net's preservation-only answer serialization step.

Return exactly the JSON object under EXACT OUTPUT OBJECT. Copy every Answer string
character-for-character. Do not paraphrase, improve, shorten, expand, reorder, or
remove any line. Do not add markdown fences, Evidence, Limits, notes, or extra keys.
The answer was already validated against source evidence; your task is exact JSON
serialization, not fact generation.

ROUTE
{route}

REQUIRED PHRASES THAT MUST REMAIN VERBATIM
{json.dumps(required, ensure_ascii=False)}

EXACT OUTPUT OBJECT
{exact_json}
"""


def install_phase19_preservation_writer(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_V1_INSTALLED"
    if module.get(marker):
        return

    writer = importlib.import_module("scripts.trace_net_h30_constrained_gemma_writer_v1")
    if not hasattr(writer, "_phase19_original_build_writer_packet"):
        writer._phase19_original_build_writer_packet = writer.build_writer_packet
        writer._phase19_original_render_writer_prompt = writer.render_writer_prompt
        writer._phase19_original_load_constrained_writer_config = writer.load_constrained_writer_config

    original_build = writer._phase19_original_build_writer_packet
    original_prompt = writer._phase19_original_render_writer_prompt
    original_config = writer._phase19_original_load_constrained_writer_config

    def build_writer_packet_v1(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        packet = dict(original_build(*args, **kwargs))
        if enabled():
            packet["phase19_preservation"] = {
                "enabled": True,
                "mode": "exact_phase3_answer_copy",
                "answer_digest_sha256": answer_digest(packet, writer.OUTPUT_SCHEMA_VERSION),
                "support_sections_source": "phase3_deterministic",
            }
        return packet

    def render_writer_prompt_v1(packet: Mapping[str, Any]) -> str:
        if not enabled():
            return original_prompt(packet)
        return build_preservation_prompt(packet, writer.OUTPUT_SCHEMA_VERSION)

    def load_config_v1(environ: Mapping[str, str] | None = None) -> Dict[str, Any]:
        config = dict(original_config(environ))
        env = os.environ if environ is None else environ
        raw_enabled = str(env.get("TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED", "0")).strip().lower()
        if raw_enabled in {"1", "true", "yes", "on"}:
            try:
                configured = int(str(env.get("TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS", max_tokens())).strip())
            except (TypeError, ValueError):
                configured = max_tokens()
            config["max_tokens"] = max(128, min(int(config.get("max_tokens") or 512), configured, 1024))
            config["phase19_preservation_enabled"] = True
        else:
            config["phase19_preservation_enabled"] = False
        return config

    writer.build_writer_packet = build_writer_packet_v1
    writer.render_writer_prompt = render_writer_prompt_v1
    writer.load_constrained_writer_config = load_config_v1

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health

    def process_v1(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        constrained = result.get("constrained_gemma_writer") if isinstance(result.get("constrained_gemma_writer"), Mapping) else {}
        result["phase19_preservation_writer"] = {
            "status": STATUS,
            "module": MODULE,
            "patch_id": PATCH_ID,
            "enabled": enabled(),
            "active": bool(enabled() and constrained.get("call_attempted")),
            "mode": "exact_phase3_answer_copy" if enabled() else "legacy_prompt",
            "max_tokens": max_tokens() if enabled() else constrained.get("max_tokens"),
            "model_call_count": int(constrained.get("call_count") or 0),
            "structured_output_accepted": bool(constrained.get("structured_output_accepted")),
            "phase3_fallback_used": bool(constrained.get("phase3_fallback_used")),
            "read_only": True,
            "support_sections_source": "phase3_deterministic",
            "source_truth_mutation_allowed": False,
        }
        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result["phase19_preservation_writer"] = {
            "status": STATUS,
            "enabled": enabled(),
            "mode": "exact_phase3_answer_copy",
            "max_tokens": max_tokens(),
            "single_model_call_maximum": True,
            "phase3_fallback_preserved": True,
            "support_sections_source": "phase3_deterministic",
            "source_truth_mutation_allowed": False,
        }
        return result

    runtime_cls.process = process_v1
    runtime_cls.health = health_v1
    module[marker] = True


__all__ = [
    "MODULE",
    "STATUS",
    "PATCH_ID",
    "enabled",
    "max_tokens",
    "canonical_answer_object",
    "answer_digest",
    "build_preservation_prompt",
    "install_phase19_preservation_writer",
]
