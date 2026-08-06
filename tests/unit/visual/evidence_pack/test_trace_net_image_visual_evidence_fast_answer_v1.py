import json
from pathlib import Path

from tiff.trace_net_image_visual_evidence_pack_v1 import main as pack_main
from tiff.trace_net_image_visual_evidence_pack_v1_check import main as pack_check_main
from tiff.trace_net_image_diagram_fast_answer_composer_v1 import main as composer_main
from tiff.trace_net_image_diagram_fast_answer_composer_v1_check import main as composer_check_main


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def linker_fixture(tmp_path: Path) -> Path:
    p = tmp_path / "linker.json"
    write_json(p, {
        "quality_status": "PASS",
        "records": [
            {
                "record_id": "link_69",
                "page_id": "t_p_120_1176_p000315",
                "page_number": 315,
                "figure": "69",
                "callout": "",
                "linked": True,
                "link_confidence": "MEDIUM",
                "link_reason": "figure_and_page_match",
                "linked_part_number": "120-50645-005",
                "linked_description": "",
                "proof_source": "trusted_ocr_table_figure_item_evidence",
                "source_trace_ready": True,
                "citation_ready": True,
                "source_trace": {"page_id": "t_p_120_1176_p000315", "source_module": "test"},
            },
            {
                "record_id": "low_1",
                "page_id": "t_p_120_1176_p000498",
                "page_number": 498,
                "figure": "608",
                "callout": "",
                "linked": False,
                "link_confidence": "LOW",
                "link_reason": "visual_or_ocr_label_no_unique_trusted_match",
                "source_trace_ready": False,
                "citation_ready": False,
            },
        ],
    })
    return p


def test_pack_builds_linked_and_unlinked_records(tmp_path):
    linker = linker_fixture(tmp_path)
    out = tmp_path / "pack"
    rc = pack_main([
        "--visual-callout-linker-v2", str(linker),
        "--output-dir", str(out),
        "--min-visual-evidence-records", "2",
        "--min-linked-visual-evidence", "1",
        "--min-source-trace-ready", "1",
        "--min-citation-ready", "1",
    ])
    assert rc == 0
    payload = json.loads((out / "trace_net_image_visual_evidence_pack_v1.json").read_text())
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["linked_visual_evidence_count"] == 1
    assert payload["summary"]["unlinked_visual_candidate_count"] == 1
    assert payload["summary"]["answer_permission_count"] == 0
    assert payload["records"][0]["citation_label"] == "V1"


def test_pack_check_passes(tmp_path):
    linker = linker_fixture(tmp_path)
    out = tmp_path / "pack"
    assert pack_main(["--visual-callout-linker-v2", str(linker), "--output-dir", str(out)]) == 0
    assert pack_check_main([
        "--pack", str(out / "trace_net_image_visual_evidence_pack_v1.json"),
        "--require-quality-pass",
        "--min-linked-visual-evidence", "1",
        "--min-source-trace-ready", "1",
        "--min-citation-ready", "1",
    ]) == 0


def test_composer_answers_linked_figure(tmp_path):
    linker = linker_fixture(tmp_path)
    pack_dir = tmp_path / "pack"
    comp_dir = tmp_path / "composer"
    assert pack_main(["--visual-callout-linker-v2", str(linker), "--output-dir", str(pack_dir)]) == 0
    rc = composer_main([
        "--image-visual-evidence-pack", str(pack_dir / "trace_net_image_visual_evidence_pack_v1.json"),
        "--question", "What does figure 69 show?",
        "--output-dir", str(comp_dir),
        "--require-webui-answer-ready",
        "--min-citations", "1",
        "--min-source-trace-ready-citations", "1",
    ])
    assert rc == 0
    payload = json.loads((comp_dir / "trace_net_image_diagram_fast_answer_composer_v1.json").read_text())
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["webui_answer_ready"] is True
    assert "120-50645-005" in payload["answer"]
    assert "[V1]" in payload["answer"]
    assert "does not prove interchangeability" in payload["answer"]


def test_composer_rejects_unlinked_figure_with_required_ready(tmp_path):
    linker = linker_fixture(tmp_path)
    pack_dir = tmp_path / "pack"
    comp_dir = tmp_path / "composer"
    assert pack_main(["--visual-callout-linker-v2", str(linker), "--output-dir", str(pack_dir)]) == 0
    rc = composer_main([
        "--image-visual-evidence-pack", str(pack_dir / "trace_net_image_visual_evidence_pack_v1.json"),
        "--question", "What does figure 608 show?",
        "--output-dir", str(comp_dir),
        "--require-webui-answer-ready",
        "--min-citations", "1",
    ])
    assert rc == 1
    payload = json.loads((comp_dir / "trace_net_image_diagram_fast_answer_composer_v1.json").read_text())
    assert payload["summary"]["webui_answer_ready"] is False
    assert "cannot identify a part" in payload["answer"]


def test_composer_check_passes_for_ready_answer(tmp_path):
    linker = linker_fixture(tmp_path)
    pack_dir = tmp_path / "pack"
    comp_dir = tmp_path / "composer"
    assert pack_main(["--visual-callout-linker-v2", str(linker), "--output-dir", str(pack_dir)]) == 0
    assert composer_main([
        "--image-visual-evidence-pack", str(pack_dir / "trace_net_image_visual_evidence_pack_v1.json"),
        "--question", "What does figure 69 show?",
        "--output-dir", str(comp_dir),
        "--require-webui-answer-ready",
    ]) == 0
    assert composer_check_main([
        "--composer", str(comp_dir / "trace_net_image_diagram_fast_answer_composer_v1.json"),
        "--require-quality-pass",
        "--require-webui-answer-ready",
        "--min-citations", "1",
        "--min-source-trace-ready-citations", "1",
    ]) == 0
