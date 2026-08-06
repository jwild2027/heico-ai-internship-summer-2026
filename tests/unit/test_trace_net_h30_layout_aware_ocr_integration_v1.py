from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_answer_quality_reconstructs_q17_without_blur_claim():
    quality = load("src/trace_net/validation/answer_quality/trace_net_h30_answer_quality_v1.py", "layout_quality_integration")
    registry = [{
        "citation_id": 1,
        "class": "semantic",
        "value": "- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP",
        "identifier_blob": "- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP",
        "page_id": "t_p_120_1176_p000005",
        "page_ids": ["t_p_120_1176_p000005"],
    }]
    answer = quality._render_ocr_recovery(
        "Locate the scanned page containing this OCR clue: '- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP'. Reconstruct the surrounding text and table relationships.",
        registry,
    )
    assert "t_p_120_1176_p000005" in answer
    assert "List of Effective Pages" in answer
    assert "25-21-00" in answer
    assert "manual page 607" in answer
    assert "25-LEP" in answer
    assert "not a scan-quality or blur classification" in answer
    assert "blurred or broken" not in answer.lower()
    assert "[1]" in answer


def test_page_bridge_attaches_and_prompts_layout_reconstruction():
    bridge = load("src/trace_net/pipeline/s6_retrieval/context_build/trace_net_h30_page_content_bridge_v1.py", "layout_bridge_integration")
    raw = {
        "page_id": "t_p_120_1176_p000005",
        "ocr_sample_text": "- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP",
        "ocr_text_char_count": 49,
        "module": "tesseract",
    }
    record = bridge._ocr_artifact_record(raw, raw["page_id"])
    assert record is not None
    assert record["layout_reconstruction"]["reconstruction_available"]
    assert "List of Effective Pages" in record["layout_reconstruction_text"]
    record["citation_id"] = 3
    result = {
        "evidence_envelope": {
            "coverage": {
                "page_content": {
                    "pages": [{
                        "page_id": raw["page_id"],
                        "source_trace": {"source_resolved": True},
                        "ocr": [record],
                        "tables": [],
                        "v1_context": [],
                        "v2_context": [],
                        "v3_page_intelligence": [],
                        "visuals": [],
                        "parts": [],
                        "conflicts": [],
                    }]
                }
            }
        }
    }
    prompt = bridge.render_page_content_prompt(result)
    assert "layout reconstruction" in prompt.lower()
    assert "manual page 607" in prompt
    assert "[3]" in prompt


def test_existing_answer_quality_contract_still_loads():
    quality = load("src/trace_net/validation/answer_quality/trace_net_h30_answer_quality_v1.py", "layout_quality_load")
    assert callable(quality.install_answer_quality)
    assert callable(quality.render_quality_answer)
