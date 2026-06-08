import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_postgres_context_overlay import _normalize_seed, load_main


def test_context_overlay_normalizes_seed_edges():
    seed = {
        "snapshot_id": "snapshot:test",
        "items": [
            {"item_type": "stage", "item_key": "a", "title": "A"},
            {"item_type": "stage", "item_key": "b", "title": "B"},
        ],
        "edges": [{"source_key": "a", "edge_type": "NEXT_STAGE", "target_key": "b"}],
        "metrics": [{"metric_key": "pages", "metric_value": 509}],
    }
    normalized = _normalize_seed(seed)
    assert normalized["snapshot"]["snapshot_id"] == "snapshot:test"
    assert len(normalized["items"]) == 2
    assert len(normalized["edges"]) == 1
    assert len(normalized["metrics"]) == 1
    assert normalized["items"][0]["answer_authority"] == "none"
    assert normalized["edges"][0]["answer_authority"] == "none"


def test_context_overlay_dry_run(tmp_path: Path):
    seed_path = tmp_path / "seed.json"
    output_dir = tmp_path / "out"
    seed_path.write_text(
        json.dumps(
            {
                "snapshot_id": "snapshot:test",
                "title": "Test context",
                "items": [
                    {"item_type": "stage", "item_key": "a", "title": "A"},
                    {"item_type": "stage", "item_key": "b", "title": "B"},
                ],
                "edges": [{"source_key": "a", "edge_type": "NEXT_STAGE", "target_key": "b"}],
                "metrics": [{"metric_key": "pages", "metric_value": 509}],
            }
        ),
        encoding="utf-8",
    )
    rc = load_main(["--seed", str(seed_path), "--output-dir", str(output_dir), "--dry-run"])
    assert rc == 0
    summary = json.loads((output_dir / "trace_net_context_overlay_load_summary.json").read_text())
    assert summary["items"] == 2
    assert summary["edges"] == 1
    assert summary["metrics"] == 1
