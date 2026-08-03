from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/maintenance/benchmark/check_trace_net_graph_explorer_v2_nomenclature_fix_quality.py"

spec = importlib.util.spec_from_file_location("graph_v2_nom_quality", MODULE_PATH)
quality = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(quality)


def _write_artifacts(output_dir: Path, *, include_page_2: bool = True) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes = [
        {"id": "page:t_p_120_1176_p000001", "type": "page", "payload": {}},
        {"id": "page:t_p_120_1176_p000002", "type": "page", "payload": {}},
        {"id": "part:120-37313-001", "type": "part", "payload": {}},
        {"id": "nomenclature:nom1", "type": "nomenclature", "payload": {}},
        {"id": "page_context_v2:ctx1", "type": "page_context_v2", "payload": {}},
        {"id": "page_context_v2:ctx2", "type": "page_context_v2", "payload": {}},
    ]
    edges = [
        {
            "id": "HAS_NOMENCLATURE:part:120-37313-001->nomenclature:nom1",
            "source": "part:120-37313-001",
            "target": "nomenclature:nom1",
            "type": "HAS_NOMENCLATURE",
        },
        {
            "id": "HAS_CONTEXT_V2:page:t_p_120_1176_p000001->page_context_v2:ctx1",
            "source": "page:t_p_120_1176_p000001",
            "target": "page_context_v2:ctx1",
            "type": "HAS_CONTEXT_V2",
        },
    ]
    if include_page_2:
        edges.append(
            {
                "id": "HAS_CONTEXT_V2:page:t_p_120_1176_p000002->page_context_v2:ctx2",
                "source": "page:t_p_120_1176_p000002",
                "target": "page_context_v2:ctx2",
                "type": "HAS_CONTEXT_V2",
            }
        )
    (output_dir / "trace_net_graph_explorer_summary.json").write_text(json.dumps({"version": "test"}), encoding="utf-8")
    (output_dir / "trace_net_graph_explorer_nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    (output_dir / "trace_net_graph_explorer_edges.json").write_text(json.dumps(edges), encoding="utf-8")


def test_quality_passes_when_required_overlays_exist(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)

    result = quality.check_quality(
        tmp_path,
        min_page_nodes=2,
        min_nomenclature_nodes=1,
        min_has_nomenclature_edges=1,
        min_context_v2_pages=2,
        require_first_pages="1-2",
        fallback_doc="t_p_120_1176",
    )

    assert result["status"] == "PASS"
    assert result["has_nomenclature_edges"] == 1
    assert result["context_v2_page_count"] == 2
    assert result["required_context_v2_missing_page_count"] == 0


def test_quality_fails_when_required_context_page_missing(tmp_path: Path) -> None:
    _write_artifacts(tmp_path, include_page_2=False)

    result = quality.check_quality(
        tmp_path,
        min_page_nodes=2,
        min_nomenclature_nodes=1,
        min_has_nomenclature_edges=1,
        min_context_v2_pages=2,
        require_first_pages="1-2",
        fallback_doc="t_p_120_1176",
    )

    assert result["status"] == "FAIL"
    assert "t_p_120_1176_p000002" in result["required_context_v2_missing_pages"]
