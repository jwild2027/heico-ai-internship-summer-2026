import importlib.util
from pathlib import Path


def test_part_family_scripts_importable():
    for script in [
        "scripts/build/ingestion/build_trace_net_part_family_fast_answer_composer_v1.py",
        "scripts/maintenance/writing/check_trace_net_part_family_fast_answer_composer_v1_quality.py",
    ]:
        path = Path(script)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
