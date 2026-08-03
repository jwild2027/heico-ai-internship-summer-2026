from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace


@dataclass
class FakeSummary:
    db_path: Path = Path("local_data/db/tiff_search.db")
    export_root: Path = Path("local_data/rescarta_exports")
    changed_paths: int = 1
    matched_pages: int = 1
    unmatched_paths: int = 0
    pages_updated: int = 1
    part_mentions_updated: int = 1
    clean_pages_updated: int = 1
    catalog_rows_updated: int = 1
    canonical_parts_updated: int = 1
    rag_chunks_updated: int = 1
    stale_embeddings_deleted: int = 0
    warnings: list[str] = field(default_factory=list)


def _load_script_module():
    script = Path(__file__).resolve().parents[2] / "scripts/operations/ingestion/update_changed_page_backend.py"
    spec = importlib.util.spec_from_file_location("update_changed_page_backend_for_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changed_page_backend_runs_post_update_checks(monkeypatch) -> None:
    module = _load_script_module()
    monkeypatch.setattr(module, "load_local_config", lambda _: {"db_path": "db.sqlite", "rescarta_export_dir": "exports", "embed_model": "bge-m3:latest"})
    monkeypatch.setattr(module, "run_changed_page_backend_update", lambda **_: FakeSummary())
    calls: list[list[str]] = []

    def fake_run(argv, check=False):
        calls.append([str(item) for item in argv])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main(["--config", "local_config.yaml", "--changed-list", "changed_tiffs.txt"])

    assert rc == 0
    joined = [" ".join(call) for call in calls]
    assert any("build_rag_embeddings.py" in item for item in joined)
    assert any("report_part_catalog_qa.py" in item for item in joined)
    assert any("triage_part_catalog_qa.py" in item for item in joined)
    assert any("audit_source_links.py" in item for item in joined)
    assert any("evaluate_rag_questions.py" in item for item in joined)


def test_changed_page_backend_fails_unmatched_by_default(monkeypatch) -> None:
    module = _load_script_module()
    monkeypatch.setattr(module, "load_local_config", lambda _: {})
    monkeypatch.setattr(module, "run_changed_page_backend_update", lambda **_: FakeSummary(matched_pages=0, unmatched_paths=1))
    calls: list[list[str]] = []
    monkeypatch.setattr(module.subprocess, "run", lambda argv, check=False: calls.append(list(argv)) or SimpleNamespace(returncode=0))

    rc = module.main(["--config", "local_config.yaml"])

    assert rc == 3
    assert calls == []
