from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tiff.page_image_recognition import load_page_image_sources, run_page_image_recognition_audit


def test_page_image_sources_use_page_role_from_context(tmp_path: Path) -> None:
    export_dir = tmp_path / 'export'
    context_file = tmp_path / 'contexts.json'
    image_path = tmp_path / 'p1.tif'
    export_dir.mkdir()
    Image.new('L', (40, 40), color=255).save(image_path)
    (export_dir / 'page_index.json').write_text(
        json.dumps({'pages': [{'page_id': 'p1', 'source_image_path': str(image_path), 'source_url': 'http://source'}]}),
        encoding='utf-8',
    )
    context_file.write_text(
        json.dumps({'contexts': [{'page_id': 'p1', 'page_role': 'figure', 'summary': 'A figure page.'}]}),
        encoding='utf-8',
    )
    sources = load_page_image_sources(export_dir=export_dir, context_file=context_file, repo_root=tmp_path)
    assert sources[0].role == 'figure'
    summary, _records = run_page_image_recognition_audit(
        export_dir=export_dir,
        context_file=context_file,
        repo_root=tmp_path,
    )
    assert summary.role_counts.get('figure') == 1
